from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from quality_runner import __version__
from quality_runner.cache_modes import CacheMode, cache_directory, resolve_cache_mode
from quality_runner.incremental_analysis_cache_io import (
    atomic_write_json as _atomic_write_json,
)
from quality_runner.incremental_analysis_cache_io import (
    cache_directory_label as _cache_directory_label,
)
from quality_runner.incremental_analysis_cache_io import (
    is_safe_cache_key as _is_safe_cache_key,
)
from quality_runner.incremental_analysis_cache_io import (
    json_hash as _json_hash,
)
from quality_runner.incremental_analysis_cache_io import (
    read_source_text as _read_source_text,
)
from quality_runner.incremental_analysis_cache_io import (
    safe_cache_tree as _safe_cache_tree,
)
from quality_runner.incremental_analysis_cache_io import (
    sha256_text as _sha256_text,
)
from quality_runner.incremental_analysis_cache_io import (
    source_signature as _source_signature,
)
from quality_runner.incremental_analysis_identity import (
    configuration_identity,
    dependency_state_identity,
    scanner_implementation_identity,
)

INCREMENTAL_ANALYSIS_CACHE_SCHEMA = "quality-runner-incremental-analysis-cache-v0.1"
INCREMENTAL_ANALYSIS_CACHE_DIRECTORY = "incremental-analysis-v1"
_CACHE_INDEX_NAME = "index.json"
_MAX_CACHE_ENTRIES = 4096
_MAX_RECOMPUTED_PATH_SAMPLES = 100
AnalysisResult = dict[str, object]
AnalysisResultValidator = Callable[[AnalysisResult], bool]
AnalysisResultFactory = Callable[[], AnalysisResult]
AnalysisResultFromSourceFactory = Callable[[str], AnalysisResult]


@dataclass
class _CacheStats:
    considered_files: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    recomputed_files: int = 0
    write_failures: int = 0
    pruned_entries: int = 0
    invalidation_reasons: Counter[str] = field(default_factory=Counter)
    recomputed_paths: list[str] = field(default_factory=list)
    index_writes: int = 0
    source_bytes_read: int = 0


class IncrementalAnalysisCache:
    """Persist validated per-file scanner results with fail-closed invalidation."""

    def __init__(
        self,
        repo_root: Path,
        *,
        analysis_kind: str,
        config: Mapping[str, object],
        context: Mapping[str, object] | None = None,
        cache_mode: CacheMode | str = "repo",
        cache_root: Path | None = None,
    ) -> None:
        self._repo_root = repo_root.expanduser().resolve()
        self._analysis_kind = analysis_kind
        self._cache_mode = resolve_cache_mode(cache_mode)
        self._persist = self._cache_mode != "disabled"
        self._cache_root = cache_root.expanduser().resolve() if cache_root is not None else None
        self._context_identity = _json_hash(context or {})
        self._configuration_identity = configuration_identity(self._repo_root, config)
        self._dependency_state_identity = dependency_state_identity(self._repo_root)
        self._scanner_implementation_identity = scanner_implementation_identity()
        self._stats = _CacheStats()
        self._index: dict[str, dict[str, object]] = {}
        self._index_loaded = False
        self._index_status = "unloaded"
        self._index_dirty = False
        self._last_content_sha256: dict[str, str] = {}

    @property
    def cache_dir(self) -> Path:
        return cache_directory(
            self._repo_root,
            mode=resolve_cache_mode(self._cache_mode),
            cache_root=self._cache_root,
            component=INCREMENTAL_ANALYSIS_CACHE_DIRECTORY,
        )

    @property
    def cache_mode(self) -> CacheMode:
        return resolve_cache_mode(self._cache_mode)

    def get_or_compute(
        self,
        *,
        relative_path: str,
        source_text: str,
        compute: AnalysisResultFactory,
        validate: AnalysisResultValidator,
        content_sha256: str | None = None,
    ) -> AnalysisResult:
        self._stats.considered_files += 1
        if not self._persist:
            self._record_recomputed_path(relative_path)
            self._stats.source_bytes_read += len(source_text.encode("utf-8"))
            return compute()
        self._stats.source_bytes_read += len(source_text.encode("utf-8"))
        identity = self._identity_for_file(
            relative_path=relative_path,
            source_text=source_text,
            content_sha256=content_sha256,
        )
        self._last_content_sha256[relative_path] = str(identity["content_sha256"])
        lookup_key = f"{self._analysis_kind}:{relative_path}"
        self._load_index()
        prior = self._index.get(lookup_key)
        reasons = self._invalidation_reasons(prior, identity)
        if not reasons:
            cached = self._read_cached_result(prior, identity, validate)
            if cached is not None:
                self._stats.cache_hits += 1
                return cached
            reasons = [self._cache_read_failure_reason(prior)]
        self._record_miss(relative_path, reasons)

        result = compute()
        self._write_result(
            lookup_key=lookup_key,
            identity=identity,
            result=result,
        )
        return result

    def get_or_compute_from_path(
        self,
        *,
        relative_path: str,
        source_path: Path,
        compute: AnalysisResultFromSourceFactory,
        validate: AnalysisResultValidator,
    ) -> AnalysisResult:
        """Use file metadata to avoid reading unchanged sources on cache hits."""
        self._stats.considered_files += 1
        if not self._persist:
            source_text = _read_source_text(source_path)
            self._stats.source_bytes_read += len(source_text.encode("utf-8"))
            self._record_recomputed_path(relative_path)
            return compute(source_text)
        signature = _source_signature(source_path)
        self._load_index()
        lookup_key = f"{self._analysis_kind}:{relative_path}"
        prior = self._index.get(lookup_key)
        prior_record = prior if isinstance(prior, dict) else None
        prior_signature = (
            prior_record.get("source_signature") if prior_record is not None else None
        )
        if isinstance(prior_signature, dict) and prior_signature == signature:
            content_sha256 = prior_record.get("content_sha256") if prior_record is not None else None
            if isinstance(content_sha256, str) and content_sha256:
                identity = self._identity_for_file(
                    relative_path=relative_path,
                    source_text="",
                    content_sha256=content_sha256,
                    source_signature=signature,
                )
                reasons = self._invalidation_reasons(prior, identity)
                if not reasons:
                    cached = self._read_cached_result(prior, identity, validate)
                    if cached is not None:
                        self._stats.cache_hits += 1
                        self._last_content_sha256[relative_path] = content_sha256
                        return cached
                    reasons = [self._cache_read_failure_reason(prior)]
                self._record_miss(relative_path, reasons)
            else:
                self._record_miss(relative_path, ["cache-index-corrupt"])
        else:
            reason = "missing-entry" if prior is None else "source-stat-changed"
            self._record_miss(relative_path, [reason])

        source_text = _read_source_text(source_path)
        self._stats.source_bytes_read += len(source_text.encode("utf-8"))
        identity = self._identity_for_file(
            relative_path=relative_path,
            source_text=source_text,
            content_sha256=None,
            source_signature=signature,
        )
        self._last_content_sha256[relative_path] = str(identity["content_sha256"])
        result = compute(source_text)
        self._write_result(
            lookup_key=lookup_key,
            identity=identity,
            result=result,
        )
        return result

    def content_sha256_for(self, relative_path: str) -> str | None:
        return self._last_content_sha256.get(relative_path)

    def evidence(self, *, considered_files: int | None = None) -> dict[str, object]:
        considered = self._stats.considered_files if considered_files is None else considered_files
        if self._persist:
            self._load_index()
            self.flush()
        reason_counts = dict(sorted(self._stats.invalidation_reasons.items()))
        if not self._persist:
            status = "disabled"
        elif considered == 0:
            status = "not-needed"
        elif self._stats.write_failures:
            status = "degraded"
        elif self._stats.cache_misses == 0:
            status = "warm"
        elif any(reason != "missing-entry" for reason in reason_counts):
            status = "invalidated"
        else:
            status = "cold"
        return {
            "schema": INCREMENTAL_ANALYSIS_CACHE_SCHEMA,
            "analysis_kind": self._analysis_kind,
            "status": status,
            "cache_directory": _cache_directory_label(self.cache_dir, self._repo_root),
            "considered_files": considered,
            "cache_hits": self._stats.cache_hits,
            "cache_misses": self._stats.cache_misses,
            "recomputed_files": self._stats.recomputed_files,
            "invalidation_reasons": reason_counts,
            "recomputed_path_samples": list(self._stats.recomputed_paths),
            "recomputed_path_sample_truncated": self._stats.recomputed_files
            > len(self._stats.recomputed_paths),
            "write_failures": self._stats.write_failures,
            "pruned_entries": self._stats.pruned_entries,
            "index_status": self._index_status if self._persist else "disabled",
            "index_entries": len(self._index),
            "persisted": self._persist,
            "cache_mode": self._cache_mode,
            "cache_root": str(self.cache_dir),
            "index_writes": self._stats.index_writes,
            "source_bytes_read": self._stats.source_bytes_read,
            "identity": {
                "quality_runner_version": __version__,
                "scanner_implementation_sha256": self._scanner_implementation_identity,
                "configuration_sha256": self._configuration_identity,
                "dependency_state_sha256": self._dependency_state_identity,
                "analysis_context_sha256": self._context_identity,
                "repository_root_sha256": _sha256_text(str(self._repo_root)),
            },
            "key_fields": [
                "relative_path",
                "content_sha256",
                "quality_runner_version",
                "scanner_implementation_sha256",
                "configuration_sha256",
                "dependency_state_sha256",
                "analysis_context_sha256",
                "repository_root_sha256",
            ],
        }

    def flush(self) -> None:
        """Persist one accumulated index update after a scan, not once per file."""
        if not self._persist or not self._index_dirty:
            return
        if not _safe_cache_tree(self.cache_dir):
            self._stats.write_failures += 1
            return
        self._prune_entries()
        if not _atomic_write_json(
            self.cache_dir / _CACHE_INDEX_NAME,
            {
                "schema": INCREMENTAL_ANALYSIS_CACHE_SCHEMA,
                "entries": self._index,
            },
        ):
            self._stats.write_failures += 1
            return
        self._index_status = "ready"
        self._stats.index_writes += 1
        self._index_dirty = False

    def _identity_for_file(
        self,
        *,
        relative_path: str,
        source_text: str,
        content_sha256: str | None,
        source_signature: dict[str, int] | None = None,
    ) -> dict[str, object]:
        return {
            "analysis_kind": self._analysis_kind,
            "relative_path": relative_path,
            "content_sha256": content_sha256 or _sha256_text(source_text),
            "quality_runner_version": __version__,
            "scanner_implementation_sha256": self._scanner_implementation_identity,
            "configuration_sha256": self._configuration_identity,
            "dependency_state_sha256": self._dependency_state_identity,
            "analysis_context_sha256": self._context_identity,
            "repository_root_sha256": _sha256_text(str(self._repo_root)),
            "source_signature": source_signature,
        }

    def _load_index(self) -> None:
        if self._index_loaded:
            return
        self._index_loaded = True
        if not _safe_cache_tree(self.cache_dir):
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
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != INCREMENTAL_ANALYSIS_CACHE_SCHEMA
        ):
            self._index_status = "corrupt"
            return
        entries = payload.get("entries")
        if not isinstance(entries, dict) or not all(
            isinstance(key, str) and isinstance(value, dict) for key, value in entries.items()
        ):
            self._index_status = "corrupt"
            return
        self._index = {key: cast(dict[str, object], value) for key, value in entries.items()}
        self._index_status = "ready"

    def _invalidation_reasons(
        self,
        prior: dict[str, object] | None,
        identity: dict[str, object],
    ) -> list[str]:
        if prior is None:
            return ["missing-entry"] if self._index_status != "corrupt" else ["cache-index-corrupt"]
        if not isinstance(prior.get("cache_key"), str):
            return ["cache-index-corrupt"]
        if any(field not in prior for field in identity):
            return ["cache-index-corrupt"]
        reasons: list[str] = []
        if prior.get("content_sha256") != identity["content_sha256"]:
            reasons.append("source-content-changed")
        if prior.get("quality_runner_version") != identity["quality_runner_version"]:
            reasons.append("quality-runner-version-changed")
        if prior.get("scanner_implementation_sha256") != identity["scanner_implementation_sha256"]:
            reasons.append("scanner-implementation-changed")
        if prior.get("configuration_sha256") != identity["configuration_sha256"]:
            reasons.append("scanner-configuration-changed")
        if prior.get("dependency_state_sha256") != identity["dependency_state_sha256"]:
            reasons.append("dependency-state-changed")
        if prior.get("analysis_context_sha256") != identity["analysis_context_sha256"]:
            reasons.append("analysis-context-changed")
        if prior.get("analysis_kind") != identity["analysis_kind"]:
            reasons.append("analysis-kind-changed")
        if prior.get("relative_path") != identity["relative_path"]:
            reasons.append("source-path-changed")
        return reasons

    def _read_cached_result(
        self,
        prior: dict[str, object] | None,
        identity: dict[str, object],
        validate: AnalysisResultValidator,
    ) -> AnalysisResult | None:
        if prior is None or not _safe_cache_tree(self.cache_dir):
            return None
        cache_key = prior.get("cache_key")
        if not isinstance(cache_key, str) or not _is_safe_cache_key(cache_key):
            return None
        path = self.cache_dir / "entries" / f"{cache_key}.json"
        if path.is_symlink() or not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("schema") != INCREMENTAL_ANALYSIS_CACHE_SCHEMA:
            return None
        if payload.get("cache_key") != cache_key:
            return None
        stored_identity = payload.get("identity")
        result = payload.get("result")
        if stored_identity != identity or not isinstance(result, dict):
            return None
        typed_result = cast(AnalysisResult, result)
        try:
            return typed_result if validate(typed_result) else None
        except Exception:
            return None

    def _cache_read_failure_reason(self, prior: dict[str, object] | None) -> str:
        if not _safe_cache_tree(self.cache_dir):
            return "cache-unavailable"
        if prior is None:
            return "missing-entry"
        cache_key = prior.get("cache_key")
        if not isinstance(cache_key, str) or not _is_safe_cache_key(cache_key):
            return "cache-index-corrupt"
        path = self.cache_dir / "entries" / f"{cache_key}.json"
        return "missing-entry" if not path.exists() else "corrupt-entry"

    def _write_result(
        self,
        *,
        lookup_key: str,
        identity: dict[str, object],
        result: AnalysisResult,
    ) -> None:
        if not self._persist:
            return
        cache_key = _json_hash(identity)
        if not _safe_cache_tree(self.cache_dir):
            self._stats.write_failures += 1
            return
        entry_path = self.cache_dir / "entries" / f"{cache_key}.json"
        payload = {
            "schema": INCREMENTAL_ANALYSIS_CACHE_SCHEMA,
            "cache_key": cache_key,
            "identity": identity,
            "result": result,
        }
        if not _atomic_write_json(entry_path, payload):
            self._stats.write_failures += 1
            return
        self._index[lookup_key] = {**identity, "cache_key": cache_key}
        self._index_dirty = True
        self._index_status = "ready"

    def _prune_entries(self) -> None:
        entries_dir = self.cache_dir / "entries"
        try:
            entries = [
                path
                for path in entries_dir.glob("*.json")
                if not path.is_symlink() and path.is_file()
            ]
            if len(entries) <= _MAX_CACHE_ENTRIES:
                return
            entries.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
            removed_keys = {
                path.stem for path in entries[_MAX_CACHE_ENTRIES:] if _is_safe_cache_key(path.stem)
            }
            for path in entries[_MAX_CACHE_ENTRIES:]:
                if path.stem not in removed_keys:
                    continue
                try:
                    path.unlink()
                except OSError:
                    continue
            if removed_keys:
                self._index = {
                    lookup_key: metadata
                    for lookup_key, metadata in self._index.items()
                    if metadata.get("cache_key") not in removed_keys
                }
                self._index_dirty = True
                self._stats.pruned_entries += len(removed_keys)
        except OSError:
            return

    def _record_miss(self, relative_path: str, reasons: list[str]) -> None:
        self._stats.cache_misses += 1
        self._stats.recomputed_files += 1
        for reason in reasons:
            self._stats.invalidation_reasons[reason] += 1
        self._record_recomputed_path(relative_path)

    def _record_recomputed_path(self, relative_path: str) -> None:
        if len(self._stats.recomputed_paths) < _MAX_RECOMPUTED_PATH_SAMPLES:
            self._stats.recomputed_paths.append(relative_path)
