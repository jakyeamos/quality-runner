from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from quality_runner.fleet.discovery import _ahead_behind, _git_output


def resolve_target_branch(
    repository: dict[str, Any], *, override: str | None = None
) -> dict[str, Any]:
    checkouts = [item for item in repository.get("checkouts", []) if isinstance(item, dict)]
    branches = sorted(
        {
            branch
            for checkout in checkouts
            for branch in checkout.get("local_branches", [])
            if isinstance(branch, str) and branch
        }
    )
    selected = _select_branch(repository, branches, override)
    if selected.get("status") == "blocked":
        return selected
    target_branch = str(selected["branch"])
    source = str(selected["source"])

    attached = [
        checkout
        for checkout in checkouts
        if checkout.get("branch") == target_branch
        and checkout.get("exists") is True
        and checkout.get("working_tree") is not False
    ]
    attached.sort(key=lambda item: (item.get("dirty") is True, str(item.get("path", ""))))
    if attached and attached[0].get("dirty") is not True:
        checkout = attached[0]
        state = _target_state(checkout)
        return _target_result(target_branch, source, checkout, state)

    hosts = [
        checkout
        for checkout in checkouts
        if checkout.get("exists") is True
        and checkout.get("prunable") is False
        and _branch_head(checkout, target_branch) is not None
    ]
    # A checkout can expose the target branch ref while its working tree is
    # still on another branch. Static evidence must prefer a filesystem
    # snapshot whose checked-out HEAD is the target branch HEAD; otherwise a
    # preserved feature/baseline worktree can be reported as target evidence.
    hosts.sort(
        key=lambda item: (
            item.get("head") != _branch_head(item, target_branch),
            item.get("dirty") is True,
            str(item.get("path", "")),
        )
    )
    if not hosts:
        return {
            "branch": target_branch,
            "source": source,
            "status": "blocked",
            "reason": "target branch exists but no checkout can host disposable verification",
            "checkout_id": None,
        }
    checkout = hosts[0]
    head = _branch_head(checkout, target_branch)
    state = _branch_state(checkout, target_branch, head)
    return _target_result(target_branch, source, checkout, state, head=head)


def _select_branch(
    repository: dict[str, Any], branches: list[str], override: str | None
) -> dict[str, Any]:
    if override:
        if override not in branches:
            return {
                "branch": override,
                "source": "explicit_override",
                "status": "blocked",
                "reason": "explicit target branch is not present in a discovered checkout",
                "checkout_id": None,
            }
        return {"branch": override, "source": "explicit_override"}
    if "dev" in branches:
        return {"branch": "dev", "source": "default_dev"}
    documented = _documented_branch(repository)
    if documented is not None and documented[0] in branches:
        branch, source = documented
        return {"branch": branch, "source": source}
    remote_default = _remote_default_branch(repository, branches)
    if remote_default is not None:
        return {"branch": remote_default, "source": "remote_default"}
    if len(branches) == 1:
        return {"branch": branches[0], "source": "only_local_branch"}
    return {
        "branch": None,
        "source": "unresolved",
        "status": "blocked",
        "reason": (
            "no dev branch, documented canonical fallback, locally verified remote "
            "default, or unambiguous sole local branch was found"
        ),
        "checkout_id": None,
    }


def _target_result(
    branch: str,
    source: str,
    checkout: dict[str, Any],
    state: dict[str, Any],
    *,
    head: str | None = None,
) -> dict[str, Any]:
    return {
        "branch": branch,
        "source": source,
        "status": "ready" if state["status"] == "ready" else state["status"],
        "reason": state["reason"],
        "checkout_id": checkout.get("checkout_id"),
        "head": head or checkout.get("head"),
        "target_state": state,
    }


def _branch_head(checkout: dict[str, Any], branch: str) -> str | None:
    path = checkout.get("path")
    if not isinstance(path, str) or not path:
        return None
    return _git_output(Path(path), "rev-parse", "--verify", f"refs/heads/{branch}")


def _branch_state(checkout: dict[str, Any], branch: str, head: str | None) -> dict[str, Any]:
    if not head:
        return {
            "status": "blocked",
            "reason": "target branch has no verifiable HEAD",
            "local_head": None,
            "safe_action": "verify_local_target",
        }
    path = checkout.get("path")
    if not isinstance(path, str) or not path:
        return {
            "status": "blocked",
            "reason": "source checkout path is unavailable",
            "local_head": head,
            "safe_action": "verify_local_target",
        }
    root = Path(path)
    upstream = _git_output(
        root, "for-each-ref", "--format=%(upstream:short)", f"refs/heads/{branch}"
    )
    evidence: dict[str, Any] = {
        "local_head": head,
        "upstream": upstream,
        "upstream_head": None,
        "ahead": None,
        "behind": None,
        "safe_action": "none",
    }
    if upstream:
        upstream_head = _git_output(root, "rev-parse", "--verify", upstream)
        ahead, behind = _ahead_behind(root, upstream, head=head)
        evidence.update({"upstream_head": upstream_head, "ahead": ahead, "behind": behind})
        if upstream_head is None or ahead is None or behind is None:
            return {
                **evidence,
                "status": "blocked",
                "reason": "configured target upstream cannot be compared to the local target",
                "safe_action": "fetch_and_verify_upstream",
            }
        if ahead > 0 and behind > 0:
            return {
                **evidence,
                "status": "blocked",
                "reason": "target branch has diverged from its configured upstream",
                "safe_action": "reconcile_diverged_target",
            }
        if behind > 0:
            return {
                **evidence,
                "status": "stale",
                "reason": "target branch is behind its configured upstream",
                "safe_action": "fast_forward_local_target",
            }
    return {
        **evidence,
        "status": "ready",
        "reason": "target branch is committed and a fingerprinted checkout can host disposable verification",
    }


def _target_state(checkout: dict[str, Any]) -> dict[str, Any]:
    checks = (
        (checkout.get("exists") is not True, "target checkout does not exist"),
        (checkout.get("detached") is True, "target checkout is detached"),
        (checkout.get("prunable") is True, "target checkout is prunable"),
        (
            not isinstance(checkout.get("head"), str) or not checkout.get("head"),
            "target checkout has no verifiable HEAD",
        ),
    )
    for blocked, reason in checks:
        if blocked:
            return {
                "status": "blocked",
                "reason": reason,
                "local_head": checkout.get("head"),
                "safe_action": "verify_local_target",
            }
    state = _branch_state(checkout, str(checkout.get("branch")), str(checkout.get("head")))
    if state["status"] == "ready":
        state["reason"] = (
            "target checkout has a committed HEAD and is fingerprinted for disposable verification"
        )
    return state


def _documented_branch(repository: dict[str, Any]) -> tuple[str, str] | None:
    root = Path(str(repository.get("primary_path", ".")))
    for relative in (
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "CONTRIBUTING.md",
        ".agents/context/README.md",
    ):
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")[:100_000]
        except OSError:
            continue
        for pattern in (
            r"(?:canonical|default|primary|routine|development)\s+(?:branch|lane)[^\n]{0,80}\b(develop|trunk|main)\b",
            r"\b(develop|trunk|main)\b\s+(?:branch|is)\s+(?:the\s+)?(?:canonical|default|primary)",
        ):
            if match := re.search(pattern, text, re.IGNORECASE):
                return match.group(1), f"documented_fallback:{relative}"
    return None


def _remote_default_branch(repository: dict[str, Any], branches: list[str]) -> str | None:
    for checkout in repository.get("checkouts", []):
        if not isinstance(checkout, dict) or checkout.get("exists") is not True:
            continue
        raw_path = checkout.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            continue
        remote_head = _git_output(
            Path(raw_path), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"
        )
        if remote_head and "/" in remote_head:
            branch = remote_head.split("/", maxsplit=1)[1]
            if branch in branches:
                return branch
    return None
