from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import Any

from quality_runner.schema_constants import WORKSPACE_SNAPSHOT_SCHEMA

ALWAYS_EXCLUDED = {".git", ".quality-runner"}
DEFAULT_EXCLUDED_PARTS = {
    ".mypy_cache": "cache",
    ".next": "generated_output",
    ".pytest_cache": "cache",
    ".ruff_cache": "cache",
    ".venv": "dependency",
    "__pycache__": "cache",
    "build": "generated_output",
    "coverage": "generated_output",
    "dist": "generated_output",
    "node_modules": "dependency",
    "venv": "dependency",
}


class SnapshotError(RuntimeError):
    pass


@contextmanager
def workspace_snapshot(
    repo_root: Path,
    *,
    baseline_ref: str | None = None,
    include_paths: tuple[str, ...] = (),
) -> Iterator[tuple[Path, dict[str, Any]]]:
    repo_root = repo_root.resolve()
    repository = _repository_identity(repo_root)
    with tempfile.TemporaryDirectory(prefix="quality-runner-task-") as temporary:
        snapshot_root = Path(temporary) / "source"
        snapshot_root.mkdir()
        if baseline_ref is None:
            entries, exclusions = _copy_workspace(
                repo_root, snapshot_root, include_paths=include_paths
            )
            source = {
                "kind": "workspace",
                "head_sha": repository["head_sha"],
                "baseline_ref": None,
            }
        else:
            revision = _resolve_revision(repo_root, baseline_ref)
            entries, exclusions = _copy_revision(
                repo_root,
                snapshot_root,
                revision,
                include_paths=include_paths,
            )
            source = {
                "kind": "git_revision",
                "head_sha": revision,
                "baseline_ref": baseline_ref,
            }
        manifest = {
            "schema": WORKSPACE_SNAPSHOT_SCHEMA,
            "repository": repository,
            "source": source,
            "entries": entries,
            "exclusions": exclusions,
            "snapshot_digest": _manifest_digest(entries),
        }
        yield snapshot_root, manifest


def changed_paths(
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> list[str]:
    old = {_entry_key(item): item for item in baseline.get("entries", [])}
    new = {_entry_key(item): item for item in current.get("entries", [])}
    paths: set[str] = set()
    for key in old.keys() | new.keys():
        if old.get(key) != new.get(key):
            paths.add(key)
    return sorted(paths)


def attach_git_metadata(repo_root: Path, snapshot_root: Path) -> None:
    """Attach local Git history without replacing the materialized workspace."""
    if (snapshot_root / ".git").exists():
        raise SnapshotError("isolated snapshot unexpectedly contains Git metadata")
    metadata_root = snapshot_root.parent / "git-metadata"
    _git(
        snapshot_root.parent,
        "clone",
        "--quiet",
        "--shared",
        "--no-checkout",
        "--",
        str(repo_root),
        str(metadata_root),
    )
    shutil.move(str(metadata_root / ".git"), str(snapshot_root / ".git"))
    metadata_root.rmdir()
    _git(snapshot_root, "read-tree", "HEAD")


def _repository_identity(repo_root: Path) -> dict[str, str]:
    top = _git(repo_root, "rev-parse", "--show-toplevel").strip()
    if Path(top).resolve() != repo_root:
        raise SnapshotError(f"repository path must be the Git root: {repo_root}")
    head = _git(repo_root, "rev-parse", "HEAD").strip()
    common_dir = _git(repo_root, "rev-parse", "--git-common-dir").strip()
    identity = hashlib.sha256(str(Path(common_dir).resolve()).encode()).hexdigest()
    return {
        "root": str(repo_root),
        "identity": identity,
        "head_sha": head,
    }


def _resolve_revision(repo_root: Path, baseline_ref: str) -> str:
    if not baseline_ref or baseline_ref.startswith("-"):
        raise SnapshotError("baseline ref must be a non-option Git revision")
    return _git(
        repo_root,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{baseline_ref}^{{commit}}",
    ).strip()


def _copy_workspace(
    repo_root: Path,
    snapshot_root: Path,
    *,
    include_paths: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    payload = _git_bytes(
        repo_root,
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
    )
    entries: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = [
        {"path": name, "reason": "quality_runner_internal"} for name in sorted(ALWAYS_EXCLUDED)
    ]
    for raw in sorted(item for item in payload.split(b"\0") if item):
        path = _decode_git_path(raw)
        exclusion = _exclusion_reason(path, include_paths)
        if exclusion is not None:
            exclusions.append({"path": path, "reason": exclusion})
            continue
        source = repo_root / path
        target = snapshot_root / path
        if not source.exists() and not source.is_symlink():
            entries.append({"path": path, "kind": "deleted"})
            continue
        entries.append(_copy_entry(source, target, path))
    return entries, _deduplicate_exclusions(exclusions)


def _copy_revision(
    repo_root: Path,
    snapshot_root: Path,
    revision: str,
    *,
    include_paths: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    payload = _git_bytes(repo_root, "ls-tree", "-r", "-z", "--full-tree", revision)
    entries: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = [
        {"path": name, "reason": "quality_runner_internal"} for name in sorted(ALWAYS_EXCLUDED)
    ]
    for record in (item for item in payload.split(b"\0") if item):
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split(" ")
        path = _decode_git_path(raw_path)
        exclusion = _exclusion_reason(path, include_paths)
        if exclusion is not None:
            exclusions.append({"path": path, "reason": exclusion})
            continue
        if object_type != "blob":
            raise SnapshotError(f"unsafe Git entry type for {path}: {object_type}")
        content = _git_bytes(repo_root, "cat-file", "blob", object_id)
        target = snapshot_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "120000":
            link_target = content.decode("utf-8", errors="strict")
            _validate_symlink(path, link_target)
            target.symlink_to(link_target)
            entries.append(
                {
                    "path": path,
                    "kind": "symlink",
                    "mode": mode,
                    "target": link_target,
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
            continue
        if mode not in {"100644", "100755"}:
            raise SnapshotError(f"unsafe Git mode for {path}: {mode}")
        target.write_bytes(content)
        os.chmod(target, 0o755 if mode == "100755" else 0o644)
        entries.append(
            {
                "path": path,
                "kind": "file",
                "mode": mode,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    return entries, exclusions


def _copy_entry(source: Path, target: Path, relative_path: str) -> dict[str, Any]:
    try:
        info = source.lstat()
    except OSError as error:
        raise SnapshotError(f"unreadable workspace entry {relative_path}: {error}") from error
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(info.st_mode)
    if stat.S_ISLNK(info.st_mode):
        link_target = os.readlink(source)
        _validate_symlink(relative_path, link_target)
        target.symlink_to(link_target)
        raw_target = link_target.encode()
        return {
            "path": relative_path,
            "kind": "symlink",
            "mode": "120000",
            "target": link_target,
            "sha256": hashlib.sha256(raw_target).hexdigest(),
        }
    if not stat.S_ISREG(info.st_mode):
        raise SnapshotError(f"unsafe workspace entry type: {relative_path}")
    try:
        content = source.read_bytes()
    except OSError as error:
        raise SnapshotError(f"unreadable workspace entry {relative_path}: {error}") from error
    target.write_bytes(content)
    os.chmod(target, mode)
    return {
        "path": relative_path,
        "kind": "file",
        "mode": "100755" if mode & 0o111 else "100644",
        "sha256": hashlib.sha256(content).hexdigest(),
        "size": len(content),
    }


def _validate_symlink(path: str, link_target: str) -> None:
    target = PurePosixPath(link_target)
    if target.is_absolute():
        raise SnapshotError(f"absolute symlink target is unsafe: {path}")
    resolved = PurePosixPath(path).parent.joinpath(target)
    depth = 0
    for part in resolved.parts:
        if part == "..":
            depth -= 1
        elif part not in {"", "."}:
            depth += 1
        if depth < 0:
            raise SnapshotError(f"symlink target escapes the repository: {path}")


def _decode_git_path(raw: bytes) -> str:
    try:
        path = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SnapshotError("non-UTF-8 repository paths are unsupported") from error
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or path in {"", "."}:
        raise SnapshotError(f"unsafe repository path: {path!r}")
    return path


def _exclusion_reason(path: str, include_paths: tuple[str, ...]) -> str | None:
    parts = set(PurePosixPath(path).parts)
    if parts & ALWAYS_EXCLUDED:
        return "quality_runner_internal"
    if any(fnmatch(path, pattern) for pattern in include_paths):
        return None
    for part, reason in DEFAULT_EXCLUDED_PARTS.items():
        if part in parts:
            return reason
    return None


def _deduplicate_exclusions(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"path": path, "reason": reason}
        for path, reason in sorted({(item["path"], item["reason"]) for item in items})
    ]


def _entry_key(item: dict[str, Any]) -> str:
    return str(item.get("path", ""))


def _manifest_digest(entries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    return _git_bytes(repo_root, *args).decode("utf-8", errors="strict")


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SnapshotError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout
