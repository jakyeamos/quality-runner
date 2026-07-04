from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def prepare_scan_branch(
    repo_root: Path, *, checkout_most_advanced_branch: bool
) -> list[dict[str, str]]:
    root = repo_root.expanduser().resolve()
    state = _branch_state(root)
    if not state["is_repo"]:
        return []

    current_branch = _string_or_none(state.get("current_branch"))
    current_head = _string_or_none(state.get("current_head"))
    main_branch = _string_or_none(state.get("main_branch"))
    main_branch_head = _string_or_none(state.get("main_branch_head"))
    most_advanced_branch = _string_or_none(state.get("most_advanced_branch"))
    most_advanced_branch_head = _string_or_none(state.get("most_advanced_branch_head"))
    dirty = state.get("dirty") is True

    if checkout_most_advanced_branch:
        if most_advanced_branch is None:
            return [
                {
                    "code": "most_advanced_branch_unavailable",
                    "message": "Quality Runner could not identify a local most-advanced branch.",
                    "path": ".",
                }
            ]
        if current_branch == most_advanced_branch or _same_commit(
            current_head, most_advanced_branch_head
        ):
            return []
        if dirty:
            raise ValueError(
                "--checkout-most-advanced-branch requires a clean git worktree before switching"
            )
        _switch_branch(root, most_advanced_branch)
        return []

    matches_main = current_branch == main_branch or _same_commit(current_head, main_branch_head)
    matches_most_advanced = current_branch == most_advanced_branch or _same_commit(
        current_head, most_advanced_branch_head
    )
    if (
        current_branch is not None
        and not matches_main
        and not matches_most_advanced
    ):
        target = most_advanced_branch or "unknown"
        return [
            {
                "code": "checked_out_branch_not_main_or_most_advanced",
                "message": (
                    f"Current branch '{current_branch}' is neither main nor the local "
                    f"most-advanced branch '{target}'. Re-run with "
                    f"--checkout-most-advanced-branch to scan '{target}'."
                ),
                "path": ".",
            }
        ]
    return []


def _branch_state(repo_root: Path) -> dict[str, Any]:
    if _git_output(repo_root, "rev-parse", "--is-inside-work-tree") != "true":
        return {"is_repo": False}

    branches = _local_branches(repo_root)
    current_branch = _git_output(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    if current_branch == "HEAD":
        current_branch = None
    status = _git_output(repo_root, "status", "--porcelain")
    main_branch = "main" if "main" in branches else None
    most_advanced_branch = _most_advanced_branch(repo_root, branches)
    return {
        "is_repo": True,
        "current_branch": current_branch,
        "current_head": _git_output(repo_root, "rev-parse", "HEAD"),
        "main_branch": main_branch,
        "main_branch_head": _branch_head(repo_root, main_branch),
        "most_advanced_branch": most_advanced_branch,
        "most_advanced_branch_head": _branch_head(repo_root, most_advanced_branch),
        "dirty": None if status is None else bool(status),
    }


def _local_branches(repo_root: Path) -> list[str]:
    output = _git_output(
        repo_root,
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads",
    )
    if output is None:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]


def _most_advanced_branch(repo_root: Path, branches: list[str]) -> str | None:
    best_branch: str | None = None
    best_score: tuple[int, int, str] | None = None
    for branch in branches:
        commit_count = _int_git_output(repo_root, "rev-list", "--count", branch)
        commit_time = _int_git_output(repo_root, "log", "-1", "--format=%ct", branch)
        if commit_count is None or commit_time is None:
            continue
        score = (commit_count, commit_time, branch)
        if best_score is None or score > best_score:
            best_score = score
            best_branch = branch
    return best_branch


def _switch_branch(repo_root: Path, branch: str) -> None:
    result = subprocess.run(
        ["git", "switch", branch],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git switch failure"
        raise ValueError(f"could not switch to local most-advanced branch '{branch}': {detail}")


def _branch_head(repo_root: Path, branch: str | None) -> str | None:
    if branch is None:
        return None
    return _git_output(repo_root, "rev-parse", branch)


def _same_commit(left: str | None, right: str | None) -> bool:
    return left is not None and right is not None and left == right


def _int_git_output(repo_root: Path, *args: str) -> int | None:
    output = _git_output(repo_root, *args)
    if output is None:
        return None
    try:
        return int(output)
    except ValueError:
        return None


def _git_output(repo_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
