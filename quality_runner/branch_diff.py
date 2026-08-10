from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BRANCH_DIFF_SCOPE_BASIS = "branch-merge-base-and-working-tree-diff"
HEAD_REF = "HEAD"
WORKTREE_REF = "WORKTREE"


@dataclass(frozen=True)
class BranchDiffScope:
    requested_base: str
    requested_head: str
    base_commit: str
    head_commit: str
    comparison_base_commit: str
    checked_out_head_commit: str
    changed_paths: tuple[str, ...]
    working_tree_included: bool
    working_tree_changed: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "scope_basis": BRANCH_DIFF_SCOPE_BASIS,
            "requested_base": self.requested_base,
            "requested_head": self.requested_head,
            "base_commit": self.base_commit,
            "head_commit": self.head_commit,
            "comparison_base_commit": self.comparison_base_commit,
            "checked_out_head_commit": self.checked_out_head_commit,
            "head_matches_checked_out": self.head_commit == self.checked_out_head_commit,
            "changed_paths": list(self.changed_paths),
            "scope_available": bool(self.changed_paths),
            "working_tree_included": self.working_tree_included,
            "working_tree_changed": self.working_tree_changed,
        }


def refresh_scope_payload(
    focus_paths: list[str] | None,
    scope_metadata: dict[str, object] | None,
) -> dict[str, object]:
    if scope_metadata is None:
        return {}
    return {
        "scan_scope": {
            "mode": "branch-diff",
            "paths": list(focus_paths or []),
            "provenance": dict(scope_metadata),
        }
    }


def resolve_branch_diff(
    repo_root: Path,
    *,
    base_ref: str,
    head_ref: str = HEAD_REF,
    include_working_tree: bool = True,
) -> BranchDiffScope:
    """Resolve a branch comparison and its current checkout path scope.

    The committed portion uses the merge-base-to-head comparison, equivalent to
    the changes contributed by the head branch relative to the base branch. The
    working tree is included only after the requested head is proven to be the
    checked-out commit, so findings cannot be attributed to the wrong branch.
    """

    root = repo_root.expanduser().resolve()
    if _git_output(root, "rev-parse", "--is-inside-work-tree") != "true":
        raise ValueError(f"not a git worktree: {root}")

    checked_out_head = _resolve_commit(root, HEAD_REF)
    base_commit = _resolve_commit(root, base_ref)
    if head_ref in {HEAD_REF, WORKTREE_REF}:
        head_commit = checked_out_head
    else:
        head_commit = _resolve_commit(root, head_ref)
    if head_commit != checked_out_head:
        raise ValueError(
            "branch diff head does not match the checked-out HEAD: "
            f"requested {head_ref} resolved to {head_commit}, checked out {checked_out_head}"
        )

    comparison_base = _git_output(root, "merge-base", base_commit, head_commit)
    committed_paths = _git_names(
        root,
        "diff",
        "--name-only",
        "--no-renames",
        comparison_base,
        head_commit,
        "--",
    )
    worktree_paths = (
        _git_names(root, "diff", "--name-only", HEAD_REF, "--")
        if include_working_tree
        else []
    )
    untracked_paths = (
        _git_names(root, "ls-files", "--others", "--exclude-standard", "--")
        if include_working_tree
        else []
    )
    changed_paths = _clean_paths((*committed_paths, *worktree_paths, *untracked_paths))
    working_tree_changed = bool(_clean_paths((*worktree_paths, *untracked_paths)))
    return BranchDiffScope(
        requested_base=base_ref,
        requested_head=head_ref,
        base_commit=base_commit,
        head_commit=head_commit,
        comparison_base_commit=comparison_base,
        checked_out_head_commit=checked_out_head,
        changed_paths=changed_paths,
        working_tree_included=include_working_tree,
        working_tree_changed=working_tree_changed,
    )


def _resolve_commit(repo_root: Path, ref: str) -> str:
    if not ref.strip():
        raise ValueError("git branch diff refs must be non-empty strings")
    return _git_output(
        repo_root,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{ref}^{{commit}}",
    )


def _clean_paths(paths: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(sorted({path for path in paths if path and not path.startswith(".quality-runner/")}))


def _git_names(repo_root: Path, *args: str) -> list[str]:
    output = _git_output(repo_root, *args)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _git_output(repo_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"git branch diff command unavailable: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise ValueError(f"git branch diff command failed: {detail}")
    return result.stdout.strip()
