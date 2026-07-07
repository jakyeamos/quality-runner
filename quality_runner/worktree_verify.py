from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quality_runner.artifacts import _validate_run_id
from quality_runner.read_only_git import _is_git_worktree

WORKTREE_MODES = frozenset({"in-place", "disposable"})


@dataclass(frozen=True)
class WorktreeSession:
    mode: str
    repo_root: Path
    execution_root: Path
    verification_context: dict[str, Any]
    mutations_isolated: bool


def resolve_worktree_mode(mode: str | None) -> str:
    resolved = mode or "in-place"
    if resolved not in WORKTREE_MODES:
        raise ValueError("worktree_mode must be in-place or disposable")
    return resolved


@contextmanager
def gate_worktree_session(
    *,
    repo_root: Path,
    run_id: str,
    worktree_mode: str = "in-place",
    allow_dirty_worktree_verify: bool = False,
) -> Iterator[WorktreeSession]:
    resolved_mode = resolve_worktree_mode(worktree_mode)
    if resolved_mode == "in-place":
        yield _in_place_session(repo_root)
        return

    session = _open_disposable_worktree(
        repo_root=repo_root,
        run_id=run_id,
        allow_dirty_worktree_verify=allow_dirty_worktree_verify,
    )
    try:
        yield session
    finally:
        _close_disposable_worktree(repo_root=repo_root, worktree_path=session.execution_root)


def _in_place_session(repo_root: Path) -> WorktreeSession:
    base_head = _git_head(repo_root)
    return WorktreeSession(
        mode="in-place",
        repo_root=repo_root,
        execution_root=repo_root,
        verification_context={
            "worktree_mode": "in-place",
            **_optional_string("base_head", base_head),
            "execution_root": ".",
            "mutations_isolated": False,
        },
        mutations_isolated=False,
    )


def _open_disposable_worktree(
    *,
    repo_root: Path,
    run_id: str,
    allow_dirty_worktree_verify: bool,
) -> WorktreeSession:
    root = repo_root.expanduser().resolve()
    if not _is_git_worktree(root):
        raise ValueError("disposable worktree mode requires a git repository")

    dirty = _is_dirty_worktree(root)
    if dirty and not allow_dirty_worktree_verify:
        raise ValueError(
            "disposable worktree verification requires a clean git worktree; "
            "pass --allow-dirty-worktree-verify to verify HEAD while preserving local edits"
        )

    base_head = _git_head(root)
    if base_head is None:
        raise ValueError("disposable worktree mode requires a readable git HEAD")

    _validate_run_id(run_id)
    worktree_path = _prepare_worktree_dir(root, run_id)
    _remove_worktree_if_registered(root, worktree_path)
    if worktree_path.exists():
        _remove_worktree_path(worktree_path)

    _git(root, "worktree", "add", "--detach", str(worktree_path), base_head)
    relative_execution_root = worktree_path.relative_to(root).as_posix()
    return WorktreeSession(
        mode="disposable",
        repo_root=root,
        execution_root=worktree_path,
        verification_context={
            "worktree_mode": "disposable",
            "base_head": base_head,
            "execution_root": relative_execution_root,
            "mutations_isolated": True,
            "dirty_source_worktree": dirty,
        },
        mutations_isolated=True,
    )


def _close_disposable_worktree(*, repo_root: Path, worktree_path: Path) -> None:
    if not worktree_path.exists():
        return
    _remove_worktree_if_registered(repo_root, worktree_path)
    if worktree_path.exists():
        _remove_worktree_path(worktree_path)
    _git_optional(repo_root, "worktree", "prune")


def _prepare_worktree_dir(repo_root: Path, run_id: str) -> Path:
    current = repo_root
    for segment in (".quality-runner", "worktrees", run_id):
        current = current / segment
        if current.is_symlink():
            raise ValueError("worktree path component must not be a symlink")
        if current.exists() and not current.is_dir():
            raise ValueError("worktree path component must be a directory")
        if not current.exists():
            current.mkdir()
    return current


def _remove_worktree_if_registered(repo_root: Path, worktree_path: Path) -> None:
    listed = _git_optional(repo_root, "worktree", "list", "--porcelain")
    if listed is None:
        return
    normalized = worktree_path.resolve().as_posix()
    for block in listed.split("\n\n"):
        worktree_line = next(
            (line for line in block.splitlines() if line.startswith("worktree ")), ""
        )
        if not worktree_line:
            continue
        registered = Path(worktree_line.removeprefix("worktree ")).resolve().as_posix()
        if registered == normalized:
            _git(repo_root, "worktree", "remove", "--force", str(worktree_path))


def _remove_worktree_path(worktree_path: Path) -> None:
    if worktree_path.is_symlink():
        raise ValueError("worktree path must not be a symlink")
    for child in sorted(worktree_path.rglob("*"), reverse=True):
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    worktree_path.rmdir()


def _is_dirty_worktree(repo_root: Path) -> bool:
    if not _is_git_worktree(repo_root):
        return False
    status = _git_optional(repo_root, "status", "--porcelain")
    return bool(status and status.strip())


def _git_head(repo_root: Path) -> str | None:
    output = _git_optional(repo_root, "rev-parse", "HEAD")
    return output.strip() if output else None


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _git_optional(repo_root: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _optional_string(key: str, value: str | None) -> dict[str, str]:
    if value is None:
        return {}
    return {key: value}
