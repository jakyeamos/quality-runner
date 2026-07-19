from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path


def safe_cache_tree(cache_dir: Path) -> bool:
    current = cache_dir
    components: list[Path] = []
    while current != current.parent:
        components.append(current)
        current = current.parent
        if len(components) > 64:
            break
    for component in reversed(components):
        if component.is_symlink():
            return False
    entries = cache_dir / "entries"
    return not entries.exists() or entries.is_dir() and not entries.is_symlink()


def cache_directory_label(cache_dir: Path, repo_root: Path) -> str:
    try:
        return str(cache_dir.relative_to(repo_root))
    except ValueError:
        return str(cache_dir)


def atomic_write_json(path: Path, payload: Mapping[str, object]) -> bool:
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


def is_safe_cache_key(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_signature(path: Path) -> dict[str, int]:
    try:
        stat = path.stat()
    except OSError:
        return {"size": -1, "mtime_ns": -1, "ctime_ns": -1, "inode": -1}
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
        "inode": stat.st_ino,
    }


def read_source_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def json_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return sha256_text(payload)
