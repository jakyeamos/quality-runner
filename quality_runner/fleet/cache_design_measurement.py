from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


class SurfaceSpecLike(Protocol):
    @property
    def path(self) -> str: ...

    @property
    def storage_class(self) -> str: ...

    @property
    def lifecycle(self) -> str: ...

    @property
    def source(self) -> str: ...

    @property
    def max_bytes(self) -> int | None: ...

    @property
    def max_entries(self) -> int | None: ...

    @property
    def max_age_days(self) -> int | None: ...


def measure_tree(
    root: Path,
    start: Path,
    *,
    excluded: set[Path],
    max_entries: int,
    deadline: float,
) -> dict[str, Any]:
    stack = [start]
    seen_inodes: set[tuple[int, int]] = set()
    logical_bytes = allocated_bytes = shared_allocated_bytes = 0
    file_count = shared_file_count = visited_entries = 0
    oldest: float | None = None
    newest: float | None = None
    complete = True
    warnings: list[str] = []
    while stack:
        if visited_entries >= max_entries or time.monotonic() >= deadline:
            complete = False
            warnings.append(f"{start.relative_to(root).as_posix()}: traversal budget exhausted")
            break
        current = stack.pop()
        if current in excluded:
            continue
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            complete = False
            warnings.append(f"{current.relative_to(root).as_posix()}: {type(error).__name__}")
            continue
        for entry in entries:
            visited_entries += 1
            if visited_entries > max_entries:
                complete = False
                break
            path = Path(entry.path)
            if path in excluded:
                continue
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError as error:
                complete = False
                warnings.append(f"{path.relative_to(root).as_posix()}: {type(error).__name__}")
                continue
            inode = (int(stat.st_dev), int(stat.st_ino))
            if inode in seen_inodes:
                continue
            seen_inodes.add(inode)
            blocks = int(getattr(stat, "st_blocks", 0)) * 512
            allocated = blocks if blocks > 0 else int(stat.st_size)
            logical_bytes += int(stat.st_size)
            allocated_bytes += allocated
            file_count += 1
            if stat.st_nlink > 1:
                shared_allocated_bytes += allocated
                shared_file_count += 1
            oldest = stat.st_mtime if oldest is None else min(oldest, stat.st_mtime)
            newest = stat.st_mtime if newest is None else max(newest, stat.st_mtime)
    return {
        "logical_bytes": logical_bytes,
        "allocated_bytes": allocated_bytes,
        "exclusive_allocated_bytes": max(allocated_bytes - shared_allocated_bytes, 0),
        "shared_allocated_bytes": shared_allocated_bytes,
        "file_count": file_count,
        "shared_file_count": shared_file_count,
        "oldest_mtime": _timestamp(oldest),
        "newest_mtime": _timestamp(newest),
        "complete": complete,
        "visited_entries": visited_entries,
        "warnings": warnings,
    }


def discover_candidates(
    root: Path,
    known_roots: list[Path],
    *,
    candidate_names: set[str],
    skip_names: set[str],
    max_entries: int,
    deadline: float,
) -> tuple[list[Path], bool, int, list[str]]:
    stack: list[tuple[Path, int]] = [(root, 0)]
    candidates: list[Path] = []
    visited = 0
    complete = True
    warnings: list[str] = []
    while stack:
        if visited >= max_entries or time.monotonic() >= deadline:
            return candidates, False, visited, [*warnings, "candidate discovery budget exhausted"]
        current, depth = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as error:
            complete = False
            warnings.append(f"{current.relative_to(root).as_posix()}: {type(error).__name__}")
            continue
        for entry in entries:
            visited += 1
            if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                continue
            path = Path(entry.path)
            if entry.name in skip_names or _inside_any(path, known_roots):
                continue
            if entry.name in candidate_names or entry.name.endswith("-cache"):
                candidates.append(path)
                continue
            if depth < 3:
                stack.append((path, depth + 1))
    return candidates, complete, visited, warnings


def surface_projection(
    spec: SurfaceSpecLike, measurement: dict[str, Any], as_of: str
) -> dict[str, Any]:
    violations: list[str] = []
    if (
        spec.max_bytes is not None
        and int(measurement["exclusive_allocated_bytes"]) > spec.max_bytes
    ):
        violations.append("max_bytes")
    if spec.max_entries is not None and int(measurement["file_count"]) > spec.max_entries:
        violations.append("max_entries")
    if spec.max_age_days is not None and _older_than(
        measurement.get("oldest_mtime"), spec.max_age_days, as_of
    ):
        violations.append("max_age_days")
    return {
        "path": spec.path,
        "class": spec.storage_class,
        "lifecycle": spec.lifecycle or "unbounded",
        "source": spec.source,
        "bounds": {
            key: value
            for key, value in {
                "max_bytes": spec.max_bytes,
                "max_entries": spec.max_entries,
                "max_age_days": spec.max_age_days,
            }.items()
            if value is not None
        },
        "bound_violations": violations,
        **measurement,
    }


def _inside_any(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _timestamp(value: float | None) -> str | None:
    return datetime.fromtimestamp(value, tz=UTC).isoformat() if value is not None else None


def _older_than(value: object, days: int, as_of: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        reference = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (reference - observed).total_seconds() > days * 86_400
