from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path
from typing import Any, TypedDict

from quality_runner.artifacts import existing_directory, prepare_directory
from quality_runner.model_audit.contracts import (
    array_value,
    digest,
    object_value,
    relative_path,
    text,
)

MAX_FILE_BYTES = 4_000_000
MAX_TOTAL_BYTES = 32_000_000
MAX_FILES = 10_000


class SnapshotFile(TypedDict):
    path: str
    sha256: str
    bytes: int


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, timeout=30, check=False
    )
    if result.returncode:
        raise ValueError("model audit requires an accessible local Git repository")
    return result.stdout


def _matches(name: str, paths: list[str]) -> bool:
    return any(path == "." or name == path or name.startswith(path + "/") for path in paths)


def _read_file(root: Path, name: str) -> bytes:
    relative_path(name)
    path = root / name
    parent = existing_directory(root, *Path(name).parts[:-1])
    descriptor = os.open(
        parent / path.name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_FILE_BYTES:
            raise ValueError("snapshot input must be a bounded regular file")
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("snapshot input exceeds file size limit")
    return data


def _copy(source: Path, target: Path, name: str) -> SnapshotFile:
    data = _read_file(source, name)
    parent = prepare_directory(target, *Path(name).parts[:-1])
    descriptor = os.open(
        parent / Path(name).name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
    return {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def capture(repo: Path, run_dir: Path, profile: dict[str, Any]) -> dict[str, Any]:
    head = _git(repo, "rev-parse", "HEAD").decode().strip()
    names = sorted(_git(repo, "ls-files", "-z").decode().rstrip("\0").split("\0"))
    selected = [
        name
        for name in names
        if _matches(name, profile["include_paths"])
        and not _matches(name, profile["exclude_paths"])
        and not name.startswith((".git/", ".quality-runner/"))
    ]
    if not selected or len(selected) > MAX_FILES:
        raise ValueError("audit scope must select between 1 and 10000 tracked files")
    target = prepare_directory(run_dir, "source")
    files: list[SnapshotFile] = []
    total = 0
    for name in selected:
        item = _copy(repo, target, name)
        total += int(item["bytes"])
        if total > MAX_TOTAL_BYTES:
            raise ValueError("audit scope exceeds the 32 MB snapshot limit; narrow the profile")
        files.append(item)
    return {
        "head": head,
        "code_digest": digest(files),
        "files": files,
        "tracked_dirty": bool(_git(repo, "status", "--porcelain", "--untracked-files=no")),
        "coverage": "explicit tracked-file selection; untracked and excluded files omitted",
    }


def validate_snapshot(run_dir: Path, snapshot: dict[str, Any]) -> None:
    source = existing_directory(run_dir, "source")
    files = [
        object_value(item, "snapshot file")
        for item in array_value(
            snapshot.get("files"), "snapshot files", minimum=1, maximum=MAX_FILES
        )
    ]
    actual: list[SnapshotFile] = []
    total = 0
    for item in files:
        name = text(item["path"], "snapshot path")
        data = _read_file(source, name)
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("snapshot exceeds total size limit")
        actual.append(
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        )
    if actual != files or digest(actual) != snapshot.get("code_digest"):
        raise ValueError("snapshot content digest mismatch")
    actual_paths = sorted(
        str(path.relative_to(source))
        for path in source.rglob("*")
        if not path.is_dir() or path.is_symlink()
    )
    if actual_paths != sorted(item["path"] for item in files):
        raise ValueError("snapshot contains unexpected or missing files")


def reuse(source_run_dir: Path, target_run_dir: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    validate_snapshot(source_run_dir, snapshot)
    target = prepare_directory(target_run_dir, "source")
    for item in snapshot["files"]:
        _copy(source_run_dir / "source", target, item["path"])
    validate_snapshot(target_run_dir, snapshot)
    return snapshot
