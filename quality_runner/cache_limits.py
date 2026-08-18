from __future__ import annotations

import os
import stat
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CachePruneResult:
    removed: tuple[Path, ...]
    retained_entries: int
    retained_allocated_bytes: int


def allocated_bytes(path: Path) -> int:
    try:
        details = path.stat(follow_symlinks=False)
    except OSError:
        return 0
    blocks = int(getattr(details, "st_blocks", 0)) * 512
    return blocks if blocks > 0 else int(details.st_size)


def prune_lru_files(
    *,
    owned_root: Path,
    cache_dir: Path,
    candidates: Iterable[Path],
    max_entries: int,
    max_bytes: int,
    reserved_bytes: int = 0,
) -> CachePruneResult:
    """Atomically detach oldest cache files without following links or leaving the owner root."""
    if max_entries < 0 or max_bytes < 0 or reserved_bytes < 0:
        raise ValueError("cache limits must be non-negative")
    root = owned_root.expanduser().absolute()
    directory = cache_dir.expanduser().absolute()
    if not _validated_owned_directory(root, directory):
        return CachePruneResult((), 0, reserved_bytes)

    rows: list[tuple[Path, int, int]] = []
    for candidate in candidates:
        path = candidate.expanduser().absolute()
        try:
            path.relative_to(directory)
        except ValueError:
            continue
        if path == directory or path.is_symlink():
            continue
        if not _validated_owned_directory(root, path.parent):
            continue
        try:
            details = path.stat(follow_symlinks=False)
        except OSError:
            continue
        if not stat.S_ISREG(details.st_mode):
            continue
        blocks = int(getattr(details, "st_blocks", 0)) * 512
        size = blocks if blocks > 0 else int(details.st_size)
        rows.append((path, int(details.st_mtime_ns), size))
    rows.sort(key=lambda row: (row[1], row[0].name), reverse=True)

    retained_count = 0
    retained_bytes = reserved_bytes
    removed: list[Path] = []
    for path, _mtime, size in rows:
        if retained_count < max_entries and retained_bytes + size <= max_bytes:
            retained_count += 1
            retained_bytes += size
            continue
        tombstone = directory / f".qr-prune-{os.getpid()}-{uuid.uuid4().hex}-{path.name}"
        try:
            path.rename(tombstone)
            tombstone.unlink()
        except OSError:
            continue
        removed.append(path)
    return CachePruneResult(tuple(removed), retained_count, retained_bytes)


def prune_lru_tree(
    *, owned_root: Path, max_entries: int, max_bytes: int, traversal_budget: int = 100_000
) -> CachePruneResult:
    root = owned_root.expanduser().absolute()
    if not _validated_owned_directory(root, root):
        return CachePruneResult((), 0, 0)
    stack = [root]
    files: list[Path] = []
    visited = 0
    while stack and visited < traversal_budget:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            visited += 1
            if visited > traversal_budget or entry.is_symlink():
                continue
            path = Path(entry.path)
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files.append(path)
            except OSError:
                continue
    return prune_lru_files(
        owned_root=root,
        cache_dir=root,
        candidates=files,
        max_entries=max_entries,
        max_bytes=max_bytes,
    )


def _validated_owned_directory(owned_root: Path, cache_dir: Path) -> bool:
    if owned_root.resolve(strict=False) != owned_root:
        return False
    try:
        cache_dir.relative_to(owned_root)
    except ValueError:
        return False
    current = cache_dir
    while True:
        if current.is_symlink():
            return False
        if current == owned_root:
            return True
        if current == current.parent:
            return False
        current = current.parent
