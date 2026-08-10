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
    if attached:
        checkout = attached[0]
        state = _target_state(checkout)
        return _target_result(target_branch, source, checkout, state)

    hosts = [
        checkout
        for checkout in checkouts
        if checkout.get("exists") is True
        and checkout.get("dirty") is not True
        and checkout.get("prunable") is False
        and _branch_head(checkout, target_branch) is not None
    ]
    hosts.sort(key=lambda item: str(item.get("path", "")))
    if not hosts:
        return {
            "branch": target_branch,
            "source": source,
            "status": "blocked",
            "reason": "target branch exists but no clean checkout can host disposable verification",
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
    state: dict[str, str],
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


def _branch_state(checkout: dict[str, Any], branch: str, head: str | None) -> dict[str, str]:
    if not head:
        return {"status": "blocked", "reason": "target branch has no verifiable HEAD"}
    path = checkout.get("path")
    if not isinstance(path, str) or not path:
        return {"status": "blocked", "reason": "source checkout path is unavailable"}
    root = Path(path)
    upstream = _git_output(
        root, "for-each-ref", "--format=%(upstream:short)", f"refs/heads/{branch}"
    )
    if upstream:
        _, behind = _ahead_behind(root, upstream, head=head)
        if behind and behind > 0:
            return {"status": "stale", "reason": "target branch is behind its configured upstream"}
    return {
        "status": "ready",
        "reason": "target branch is committed and a clean checkout can host disposable verification",
    }


def _target_state(checkout: dict[str, Any]) -> dict[str, str]:
    checks = (
        (checkout.get("exists") is not True, "target checkout does not exist"),
        (checkout.get("detached") is True, "target checkout is detached"),
        (checkout.get("prunable") is True, "target checkout is prunable"),
        (checkout.get("dirty") is True, "target checkout is dirty"),
        (
            not isinstance(checkout.get("head"), str) or not checkout.get("head"),
            "target checkout has no verifiable HEAD",
        ),
        (checkout.get("stale") is True, "target checkout is behind its configured upstream"),
    )
    for blocked, reason in checks:
        if blocked:
            return {"status": "stale" if "behind" in reason else "blocked", "reason": reason}
    return {"status": "ready", "reason": "target checkout is clean, attached, and verifiable"}


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
