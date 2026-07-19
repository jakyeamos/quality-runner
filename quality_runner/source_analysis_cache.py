from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Sequence
from contextlib import suppress
from pathlib import Path

from quality_runner.cache_modes import CacheMode, cache_directory, resolve_cache_mode

SOURCE_ANALYSIS_CACHE_SCHEMA = "quality-runner-source-analysis-cache-v0.1"
_CACHE_DIRECTORY = "source-analysis-v1"
_MAX_CACHE_ENTRIES = 1024
_CACHE_PRUNE_HEADROOM = 64


class SourceAnalysisCache:
    """Reuse redacted source lines by content hash without touching source files."""

    def __init__(
        self,
        repo_root: Path,
        *,
        cache_mode: CacheMode | str = "repo",
        cache_root: Path | None = None,
    ) -> None:
        self._repo_root = repo_root.expanduser().resolve()
        self._cache_mode = resolve_cache_mode(cache_mode)
        self._cache_root = cache_root.expanduser().resolve() if cache_root is not None else None
        self._redacted_by_hash: dict[str, list[str]] = {}

    def redacted_lines_for_source(
        self,
        *,
        source_text: str,
        source_lines: Sequence[str],
        redactor: Callable[[Sequence[str]], list[str]],
    ) -> list[str]:
        content_sha256 = _content_sha256(source_text)
        if content_sha256 in self._redacted_by_hash:
            redacted_lines = self._redacted_by_hash[content_sha256]
            return list(redacted_lines)

        cached_lines = self._load(content_sha256)
        if cached_lines is not None:
            self._redacted_by_hash[content_sha256] = cached_lines
            return list(cached_lines)

        redacted_lines = redactor(source_lines)
        self._redacted_by_hash[content_sha256] = list(redacted_lines)
        self._store(content_sha256, redacted_lines)
        return list(redacted_lines)

    def redacted_lines_for_path(
        self,
        path: Path,
        *,
        redactor: Callable[[Sequence[str]], list[str]],
    ) -> list[str] | None:
        try:
            source_text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        return self.redacted_lines_for_source(
            source_text=source_text,
            source_lines=source_text.splitlines(),
            redactor=redactor,
        )

    @property
    def cache_dir(self) -> Path:
        return cache_directory(
            self._repo_root,
            mode=resolve_cache_mode(self._cache_mode),
            cache_root=self._cache_root,
            component=_CACHE_DIRECTORY,
        )

    def _load(self, content_sha256: str) -> list[str] | None:
        if self._cache_mode == "disabled" or not self._safe_cache_tree():
            return None
        path = self.cache_dir / f"{content_sha256}.json"
        if path.is_symlink() or not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("schema") != SOURCE_ANALYSIS_CACHE_SCHEMA:
            return None
        if payload.get("content_sha256") != content_sha256:
            return None
        redacted_lines = payload.get("redacted_lines")
        if not isinstance(redacted_lines, list) or not all(
            isinstance(line, str) for line in redacted_lines
        ):
            return None
        return list(redacted_lines)

    def _store(self, content_sha256: str, redacted_lines: Sequence[str]) -> None:
        if self._cache_mode == "disabled" or not self._safe_cache_tree():
            return
        cache_dir = self.cache_dir
        path = cache_dir / f"{content_sha256}.json"
        temporary_path: str | None = None
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            if cache_dir.is_symlink() or path.is_symlink():
                return
            payload: dict[str, object] = {
                "schema": SOURCE_ANALYSIS_CACHE_SCHEMA,
                "content_sha256": content_sha256,
                "redacted_lines": list(redacted_lines),
            }
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=cache_dir,
                prefix=f".{content_sha256}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = handle.name
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
            os.replace(temporary_path, path)
            temporary_path = None
            self._prune()
        except (OSError, ValueError, TypeError):
            pass
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    Path(temporary_path).unlink()

    def _safe_cache_tree(self) -> bool:
        current = self.cache_dir
        components: list[Path] = []
        while current != current.parent:
            components.append(current)
            current = current.parent
            if len(components) > 64:
                break
        return all(not component.is_symlink() for component in reversed(components))

    def _prune(self) -> None:
        cache_dir = self.cache_dir
        try:
            entries = [
                path
                for path in cache_dir.glob("*.json")
                if not path.is_symlink() and path.is_file()
            ]
            if len(entries) <= _MAX_CACHE_ENTRIES + _CACHE_PRUNE_HEADROOM:
                return
            entries.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
            for path in entries[_MAX_CACHE_ENTRIES:]:
                try:
                    path.unlink()
                except OSError:
                    continue
        except OSError:
            return


def _content_sha256(source_text: str) -> str:
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()
