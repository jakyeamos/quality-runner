from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from quality_runner import __version__
from quality_runner.code_quality_native_similarity import NATIVE_SIMILARITY_SCHEMA

SEMANTIC_SIMILARITY_CACHE_SCHEMA = "quality-runner-semantic-similarity-cache-v0.1"
CACHE_DIRECTORY = "semantic-similarity-v1"
_CACHE_INDEX_NAME = "index.json"
SimilarityMaterializer = Callable[[Mapping[str, object]], dict[str, Any]]


@dataclass
class _CacheStats:
    cache_hits: int = 0
    cache_misses: int = 0
    write_failures: int = 0
    invalidation_reasons: Counter[str] = field(default_factory=Counter)


class SemanticSimilarityCache:
    """Persist one validated similarity report per input/policy identity."""

    def __init__(
        self,
        repo_root: Path,
        *,
        cache_root: Path | None,
        persist: bool,
    ) -> None:
        self._repo_root = repo_root.expanduser().resolve()
        self._cache_root = (
            cache_root.expanduser().resolve()
            if cache_root is not None
            else self._repo_root / ".quality-runner"
        )
        self._persist = persist
        self._stats = _CacheStats()
        self._index: dict[str, dict[str, object]] = {}
        self._latest_identity: dict[str, object] | None = None
        self._index_loaded = False
        self._index_status = "unloaded"

    @property
    def cache_dir(self) -> Path:
        return self._cache_root / "cache" / CACHE_DIRECTORY

    def get(
        self,
        *,
        key: str,
        identity: Mapping[str, object],
        materialize: SimilarityMaterializer,
    ) -> dict[str, Any] | None:
        if not self._persist:
            return None
        self._load_index()
        prior = self._index.get(key)
        if prior is None:
            self._record_miss(_invalidation_reasons(self._latest_identity, identity))
            return None
        prior_identity = prior.get("identity")
        if not isinstance(prior_identity, dict):
            self._record_miss(["cache-index-corrupt"])
            return None
        reasons = _invalidation_reasons(prior_identity, identity)
        if reasons:
            self._record_miss(reasons)
            return None

        cache_path = self.cache_dir / "entries" / f"{key}.json"
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._record_miss(["corrupt-entry" if cache_path.exists() else "missing-entry"])
            return None
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != SEMANTIC_SIMILARITY_CACHE_SCHEMA
            or payload.get("cache_key") != key
            or payload.get("identity") != dict(identity)
            or not isinstance(payload.get("result"), dict)
        ):
            self._record_miss(["corrupt-entry"])
            return None
        try:
            result = materialize(cast(Mapping[str, object], payload["result"]))
        except (TypeError, ValueError, KeyError):
            self._record_miss(["corrupt-entry"])
            return None
        self._stats.cache_hits += 1
        result["cache_status"] = "hit"
        scanner_status = result.get("scanner_status")
        if isinstance(scanner_status, list):
            result["scanner_status"] = [
                {**entry, "status": "cached"} if isinstance(entry, dict) else entry
                for entry in scanner_status
            ]
        return result

    def put(
        self,
        *,
        key: str,
        identity: Mapping[str, object],
        result: Mapping[str, object],
    ) -> None:
        if not self._persist or not _safe_cache_tree(self._cache_root, self.cache_dir):
            if self._persist:
                self._stats.write_failures += 1
            return
        payload = {
            "schema": SEMANTIC_SIMILARITY_CACHE_SCHEMA,
            "cache_key": key,
            "identity": dict(identity),
            "result": dict(result),
        }
        entry_path = self.cache_dir / "entries" / f"{key}.json"
        if not _atomic_write_json(entry_path, payload):
            self._stats.write_failures += 1
            return
        self._index[key] = {"cache_key": key, "identity": dict(identity)}
        self._latest_identity = dict(identity)
        if not _atomic_write_json(
            self.cache_dir / _CACHE_INDEX_NAME,
            {
                "schema": SEMANTIC_SIMILARITY_CACHE_SCHEMA,
                "entries": self._index,
                "latest_cache_key": key,
                "latest_identity": self._latest_identity,
            },
        ):
            self._stats.write_failures += 1
            return
        self._index_status = "ready"

    def evidence(self, *, cache_status: str, considered_files: int) -> dict[str, object]:
        if self._persist:
            self._load_index()
        reasons = dict(sorted(self._stats.invalidation_reasons.items()))
        if not self._persist or cache_status == "disabled":
            status = "disabled"
        elif self._stats.write_failures:
            status = "degraded"
        elif considered_files == 0:
            status = "not-needed"
        elif self._stats.cache_misses == 0:
            status = "warm"
        elif any(reason != "missing-entry" for reason in reasons):
            status = "invalidated"
        else:
            status = "cold"
        return {
            "schema": SEMANTIC_SIMILARITY_CACHE_SCHEMA,
            "analysis_kind": "semantic-similarity",
            "status": status,
            "cache_status": cache_status,
            "cache_directory": _relative_cache_directory(self.cache_dir, self._repo_root),
            "considered_files": considered_files,
            "cache_hits": self._stats.cache_hits,
            "cache_misses": self._stats.cache_misses,
            "recomputed_files": self._stats.cache_misses,
            "invalidation_reasons": reasons,
            "recomputed_path_samples": [],
            "recomputed_path_sample_truncated": False,
            "write_failures": self._stats.write_failures,
            "pruned_entries": 0,
            "index_status": self._index_status if self._persist else "disabled",
            "index_entries": len(self._index),
            "persisted": self._persist,
            "key_fields": [
                "files",
                "policy",
                "disabled_groups",
                "quality_runner_version",
                "implementation_sha256",
            ],
        }

    def _load_index(self) -> None:
        if self._index_loaded:
            return
        self._index_loaded = True
        if not _safe_cache_tree(self._cache_root, self.cache_dir):
            self._index_status = "unavailable"
            return
        index_path = self.cache_dir / _CACHE_INDEX_NAME
        if index_path.is_symlink() or not index_path.is_file():
            self._index_status = "missing"
            return
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._index_status = "corrupt"
            return
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != SEMANTIC_SIMILARITY_CACHE_SCHEMA
            or not isinstance(entries, dict)
            or not all(
                isinstance(key, str) and isinstance(value, dict) for key, value in entries.items()
            )
        ):
            self._index_status = "corrupt"
            return
        self._index = {key: dict(value) for key, value in entries.items()}
        latest_identity = payload.get("latest_identity")
        self._latest_identity = dict(latest_identity) if isinstance(latest_identity, dict) else None
        self._index_status = "ready"

    def _record_miss(self, reasons: list[str]) -> None:
        self._stats.cache_misses += 1
        for reason in reasons:
            self._stats.invalidation_reasons[reason] += 1


def cache_identity(
    *,
    scanned_files: Sequence[Mapping[str, object]] | None,
    policy: Mapping[str, object],
    disabled_groups: set[str],
    implementation_paths: Sequence[Path],
) -> dict[str, object]:
    files = []
    for scanned_file in scanned_files or ():
        path = scanned_file.get("path")
        text = scanned_file.get("text")
        if isinstance(path, str) and isinstance(text, str):
            files.append([path, hashlib.sha256(text.encode("utf-8")).hexdigest()])
    implementation = hashlib.sha256()
    for path in implementation_paths:
        implementation.update(path.read_bytes())
    return {
        "schema": NATIVE_SIMILARITY_SCHEMA,
        "quality_runner_version": __version__,
        "implementation_sha256": implementation.hexdigest(),
        "policy": dict(policy),
        "disabled_groups": sorted(disabled_groups),
        "files": sorted(files),
    }


def cache_key(
    *,
    scanned_files: Sequence[Mapping[str, object]] | None,
    policy: Mapping[str, object],
    disabled_groups: set[str],
    implementation_paths: Sequence[Path],
) -> str:
    return _json_hash(
        cache_identity(
            scanned_files=scanned_files,
            policy=policy,
            disabled_groups=disabled_groups,
            implementation_paths=implementation_paths,
        )
    )


def _invalidation_reasons(
    prior: Mapping[str, object] | None,
    current: Mapping[str, object],
) -> list[str]:
    if prior is None:
        return ["missing-entry"]
    reasons: list[str] = []
    if prior.get("files") != current.get("files"):
        reasons.append("source-content-changed")
    if prior.get("policy") != current.get("policy") or prior.get("disabled_groups") != current.get(
        "disabled_groups"
    ):
        reasons.append("scanner-configuration-changed")
    if prior.get("quality_runner_version") != current.get("quality_runner_version"):
        reasons.append("quality-runner-version-changed")
    if prior.get("implementation_sha256") != current.get("implementation_sha256"):
        reasons.append("scanner-implementation-changed")
    return reasons


def _safe_cache_tree(cache_root: Path, cache_dir: Path) -> bool:
    if cache_root.is_symlink() or cache_dir.is_symlink():
        return False
    entries = cache_dir / "entries"
    return not entries.exists() or entries.is_dir() and not entries.is_symlink()


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or path.parent.is_symlink():
            return False
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = handle.name
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
            return True
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    Path(temporary_path).unlink()
    except (OSError, TypeError, ValueError):
        return False


def _relative_cache_directory(cache_dir: Path, repo_root: Path) -> str:
    try:
        return str(cache_dir.relative_to(repo_root))
    except ValueError:
        return str(cache_dir)


def _json_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
