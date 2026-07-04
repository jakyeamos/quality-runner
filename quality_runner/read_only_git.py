from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TrackedSnapshot:
    available: bool
    patch: str
    changed_files: tuple[str, ...]
    reason: str | None = None


def tracked_snapshot(repo_root: Path) -> TrackedSnapshot:
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
    )


def restore_if_changed(repo_root: Path, before: TrackedSnapshot | None) -> dict[str, Any] | None:
    if before is None or not before.available:
        return None
    after = tracked_snapshot(repo_root)
    if not after.available or after.patch == before.patch:
        return None
    restore_error = _restore_snapshot(repo_root=repo_root, before=before, after=after)
    restored = restore_error is None and tracked_snapshot(repo_root).patch == before.patch
    return {
        "tracked_files": sorted(set(before.changed_files) | set(after.changed_files)),
        "restored": restored,
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
