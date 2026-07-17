from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quality_runner.scan_exclusions import ALWAYS_EXCLUDED_PATH_PARTS, matches_scan_exclusion

ALLOWED_MUTATION_PATHS = (".quality-runner", ".quality-runner/runs/", ".quality-runner/worktrees/")
MAX_MANIFEST_PATHS = 2000
MAX_HASH_BYTES = 8 * 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
SNAPSHOT_EXCLUDED_DIRECTORY_PARTS = frozenset(
    {
        *ALWAYS_EXCLUDED_PATH_PARTS,
        ".cache",
        ".next",
        ".nuxt",
        ".parcel-cache",
        ".pytest_cache",
        ".ruff_cache",
        ".svelte-kit",
        ".turbo",
        ".uv-cache",
        ".vercel",
        ".vite",
        "build",
        "coverage",
        "dist",
        "out",
        "playwright-report",
        "test-results",
        "vendor",
    }
)


@dataclass(frozen=True)
class TrackedSnapshot:
    available: bool
    patch: str
    changed_files: tuple[str, ...]
    untracked_files: tuple[str, ...] = ()
    ignored_files: tuple[str, ...] = ()
    filesystem_manifest: tuple[tuple[str, str], ...] = ()
    manifest_complete: bool = True
    reason: str | None = None


def tracked_snapshot(
    repo_root: Path,
    *,
    scan_exclusions: Sequence[str] | None = None,
) -> TrackedSnapshot:
    if not _is_git_worktree(repo_root):
        return TrackedSnapshot(
            available=False,
            patch="",
            changed_files=(),
            reason="repo is not a git worktree",
        )
    try:
        patch = _git(repo_root, "diff", "--binary", "HEAD", "--")
        changed_files = tuple(_git_lines(repo_root, "diff", "--name-only", "HEAD", "--"))
        untracked_files, ignored_files, complete = _status_paths(
            repo_root,
            scan_exclusions=scan_exclusions,
        )
        manifest = _filesystem_manifest(
            repo_root,
            [*untracked_files, *ignored_files],
        )
    except subprocess.CalledProcessError:
        return TrackedSnapshot(
            available=False,
            patch="",
            changed_files=(),
            reason="repo has no readable HEAD diff",
        )
    return TrackedSnapshot(
        available=True,
        patch=patch,
        changed_files=changed_files,
        untracked_files=untracked_files,
        ignored_files=ignored_files,
        filesystem_manifest=manifest,
        manifest_complete=complete,
    )


def restore_if_changed(
    repo_root: Path,
    before: TrackedSnapshot | None,
    *,
    scan_exclusions: list[str] | None = None,
) -> dict[str, Any] | None:
    if before is None or not before.available:
        return None
    after = tracked_snapshot(repo_root, scan_exclusions=scan_exclusions)
    if not after.available:
        return None
    tracked_changed = after.patch != before.patch
    manifest_changed = (
        after.filesystem_manifest != before.filesystem_manifest
        or after.manifest_complete is False
        or before.manifest_complete is False
    )
    if not tracked_changed and not manifest_changed:
        return None
    restore_error = (
        _restore_snapshot(repo_root=repo_root, before=before, after=after)
        if tracked_changed
        else None
    )
    restored_snapshot = tracked_snapshot(repo_root, scan_exclusions=scan_exclusions)
    restored = (
        restore_error is None
        and restored_snapshot.patch == before.patch
        and restored_snapshot.filesystem_manifest == before.filesystem_manifest
    )
    changed_paths = _manifest_changed_paths(before, after)
    return {
        "tracked_files": sorted(set(before.changed_files) | set(after.changed_files))
        if tracked_changed
        else [],
        "untracked_or_ignored_files": changed_paths,
        "manifest_complete": after.manifest_complete and before.manifest_complete,
        "restored": restored,
        "allowed_paths": list(ALLOWED_MUTATION_PATHS),
        "scan_exclusions": sorted(
            item for item in (scan_exclusions or []) if isinstance(item, str) and item
        ),
        **({"restore_error": restore_error} if restore_error else {}),
    }


def _restore_snapshot(
    *,
    repo_root: Path,
    before: TrackedSnapshot,
    after: TrackedSnapshot,
) -> str | None:
    if after.patch:
        error = _git_apply(repo_root, "--reverse", after.patch)
        if error is not None:
            return error
    if before.patch:
        error = _git_apply(repo_root, None, before.patch)
        if error is not None:
            return error
    return None


def _is_git_worktree(repo_root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _git_lines(repo_root: Path, *args: str) -> list[str]:
    return [line for line in _git(repo_root, *args).splitlines() if line]


def _status_paths(
    repo_root: Path,
    *,
    scan_exclusions: Sequence[str] | None,
) -> tuple[tuple[str, ...], tuple[str, ...], bool]:
    output = _git(
        repo_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=normal",
        "--ignored=matching",
    )
    untracked: list[str] = []
    ignored: list[str] = []
    complete = True
    for record in output.split("\0"):
        if len(record) < 4:
            continue
        status = record[:2]
        path = record[3:]
        target = untracked if status == "??" else ignored if status == "!!" else None
        if target is None:
            continue
        expanded, expanded_complete = _expand_status_path(
            repo_root,
            path,
            scan_exclusions=scan_exclusions,
        )
        complete = complete and expanded_complete
        target.extend(expanded)
    if len(untracked) + len(ignored) > MAX_MANIFEST_PATHS:
        complete = False
    return (
        tuple(untracked[:MAX_MANIFEST_PATHS]),
        tuple(ignored[:MAX_MANIFEST_PATHS]),
        complete,
    )


def _expand_status_path(
    repo_root: Path,
    relative: str,
    *,
    scan_exclusions: Sequence[str] | None,
) -> tuple[list[str], bool]:
    if _snapshot_excluded_path(relative, scan_exclusions=scan_exclusions):
        return [], True
    path = repo_root / relative.rstrip("/")
    if not path.is_dir() or path.is_symlink():
        return [relative], True
    entries: list[str] = []
    complete = True
    try:
        for current_root, dir_names, file_names in os.walk(path):
            current_path = Path(current_root)
            dir_names[:] = [
                name
                for name in dir_names
                if not _snapshot_excluded_path(
                    (current_path / name).relative_to(repo_root).as_posix(),
                    scan_exclusions=scan_exclusions,
                )
            ]
            for file_name in sorted(file_names):
                child = current_path / file_name
                if child.is_symlink() or not child.is_file():
                    continue
                child_relative = child.relative_to(repo_root).as_posix()
                if _snapshot_excluded_path(child_relative, scan_exclusions=scan_exclusions):
                    continue
                if len(entries) >= MAX_MANIFEST_PATHS:
                    complete = False
                    return entries, complete
                entries.append(child_relative)
    except OSError:
        return [relative], False
    return (entries or [relative]), complete


def _filesystem_manifest(repo_root: Path, paths: list[str]) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    for relative in sorted(set(paths))[:MAX_MANIFEST_PATHS]:
        path = repo_root / relative
        if not path.is_file() or path.is_symlink():
            entries.append((relative, "missing-or-non-file"))
            continue
        digest = _file_fingerprint(path)
        entries.append((relative, digest))
    return tuple(entries)


def _file_fingerprint(path: Path) -> str:
    try:
        stat = path.stat()
        if stat.st_size > MAX_HASH_BYTES:
            return f"metadata:{stat.st_size}:{stat.st_mtime_ns}"
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(HASH_CHUNK_BYTES):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"
    except OSError:
        return "unreadable"


def _manifest_changed_paths(before: TrackedSnapshot, after: TrackedSnapshot) -> list[str]:
    before_map = dict(before.filesystem_manifest)
    after_map = dict(after.filesystem_manifest)
    return sorted(
        path
        for path in set(before_map) | set(after_map)
        if before_map.get(path) != after_map.get(path)
    )


def _allowed_mutation_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized == ALLOWED_MUTATION_PATHS[0] or normalized.startswith(
        ALLOWED_MUTATION_PATHS[1:]
    )


def _snapshot_excluded_path(
    relative: str,
    *,
    scan_exclusions: Sequence[str] | None,
) -> bool:
    normalized = relative.replace("\\", "/").strip("/")
    if not normalized or _allowed_mutation_path(normalized):
        return True
    parts = Path(normalized).parts
    if any(part in SNAPSHOT_EXCLUDED_DIRECTORY_PARTS for part in parts):
        return True
    return matches_scan_exclusion(normalized, list(scan_exclusions or ()))


def _git_apply(repo_root: Path, mode: str | None, patch: str) -> str | None:
    command = ["git", "apply", "--whitespace=nowarn", "--binary"]
    if mode is not None:
        command.append(mode)
    result = subprocess.run(
        command,
        cwd=repo_root,
        input=patch,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return None
    return result.stderr.strip() or result.stdout.strip() or "git apply failed"
