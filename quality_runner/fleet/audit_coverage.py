from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, cast

from quality_runner.fleet import audit_coverage_custody as _custody
from quality_runner.fleet.contracts import digest
from quality_runner.process_runner import run_command

AUDIT_COVERAGE_SCHEMA = "quality-runner-audit-coverage/v1"
CUSTODY_DISPOSITION_SCHEMA = _custody.CUSTODY_DISPOSITION_SCHEMA
load_custody_dispositions = _custody.load_custody_dispositions
_apply_custody_dispositions = _custody.apply_custody_dispositions
AUDIT_COVERAGE_STATUSES = frozenset(
    {"complete", "incomplete_unfolded", "blocked_ambiguous", "stale_target"}
)
MAX_COVERAGE_ITEMS = 64


def assess_audit_coverage(
    repository: dict[str, Any],
    *,
    custody_dispositions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assess whether the canonical target represents all discovered Git work."""

    target = _object(repository.get("target_branch"))
    target_branch = _text(target.get("branch"))
    target_head = _text(target.get("head"))
    root = _command_root(repository, target)
    comparisons: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    if root is not None and target_branch and target_head:
        comparisons, ambiguous = _compare_refs(root, target_branch, target_head)
        ambiguous.extend(_detached_head_gaps(repository, root, target_head))
    elif str(target.get("status", "blocked")) == "ready":
        ambiguous.append(
            {
                "kind": "target",
                "reason": "ready target metadata has no comparable branch, head, or checkout",
                "safe_action": "verify_local_target",
            }
        )

    dirty_worktrees = _dirty_worktrees(repository)
    unfolded = [item for item in comparisons if item["disposition"] == "unfolded"]
    observed_unfolded_count = len(unfolded)
    observed_dirty_count = len(dirty_worktrees)
    observed_ambiguous_count = len(ambiguous)
    excluded = [item for item in comparisons if item["disposition"] != "unfolded"]
    (
        unfolded,
        dirty_worktrees,
        ambiguous,
        dispositioned,
        disposition_errors,
    ) = _apply_custody_dispositions(
        target_head=target_head,
        unfolded=unfolded,
        dirty_worktrees=dirty_worktrees,
        ambiguous=ambiguous,
        supplied=custody_dispositions or [],
    )
    excluded.extend(dispositioned)
    status = _coverage_status(
        target_status=str(target.get("status", "blocked")),
        unfolded=unfolded,
        dirty_worktrees=dirty_worktrees,
        ambiguous=ambiguous,
        disposition_errors=disposition_errors,
    )
    payload: dict[str, Any] = {
        "schema": AUDIT_COVERAGE_SCHEMA,
        "status": status,
        "canonical_branch": target_branch,
        "canonical_head": target_head,
        "evidence_scope": "canonical_target_head",
        "canonical_findings_valid": target.get("status") == "ready" and bool(target_head),
        "comparison_eligible": status == "complete",
        "publication_ready": status == "complete",
        "unfolded_branch_count": len(unfolded),
        "dirty_worktree_count": len(dirty_worktrees),
        "ambiguous_item_count": len(ambiguous),
        "excluded_ref_count": len(excluded),
        "unfolded_branches": unfolded[:MAX_COVERAGE_ITEMS],
        "dirty_worktrees": dirty_worktrees[:MAX_COVERAGE_ITEMS],
        "ambiguous_items": ambiguous[:MAX_COVERAGE_ITEMS],
        "excluded_ref_counts": _count_dispositions(excluded),
        "observed_unfolded_branch_count": observed_unfolded_count,
        "observed_dirty_worktree_count": observed_dirty_count,
        "observed_ambiguous_item_count": observed_ambiguous_count,
        "custody_dispositioned_count": len(dispositioned),
        "custody_dispositioned_items": dispositioned[:MAX_COVERAGE_ITEMS],
        "custody_disposition_errors": disposition_errors[:MAX_COVERAGE_ITEMS],
        "safe_action": _safe_action(status),
    }
    if dispositioned:
        payload["evidence_scope"] = "canonical_target_head_with_custody_dispositions"
    payload["provenance_hash"] = digest(payload)
    return payload


def summarize_audit_coverage(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    gaps: list[str] = []
    provenance: list[tuple[str, object]] = []
    for result in results:
        repository = _object(result.get("repository"))
        # Direct callers may build summaries from pre-coverage result rows. The
        # audit producer always attaches this field before publication; absent
        # metadata here is therefore legacy helper input, not a discovered
        # ambiguous Git state. Feed construction remains strict and rejects
        # missing coverage on its publication path.
        if "audit_coverage" not in repository:
            continue
        coverage = _object(repository.get("audit_coverage"))
        status = str(coverage.get("status", "blocked_ambiguous"))
        counts[status] = counts.get(status, 0) + 1
        if status != "complete":
            gaps.append(f"{result.get('repo_id')}:audit_coverage:{status}")
        provenance.append((str(result.get("repo_id", "")), coverage))
    complete = counts.get("complete", 0)
    return {
        "summary": {
            "audit_coverage_counts": dict(sorted(counts.items())),
            "audit_coverage_complete": complete,
            "audit_coverage_incomplete": len(results) - complete,
            "canonical_publication_ready": bool(results) and complete == len(results),
        },
        "gaps": gaps,
        "provenance": [coverage for _, coverage in sorted(provenance)],
    }


def _compare_refs(
    root: Path, target_branch: str, target_head: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    refs = _git_lines(
        root,
        "for-each-ref",
        "--format=%(refname)%09%(refname:short)%09%(objectname)%09%(symref)",
        "refs/heads",
        "refs/remotes",
    )
    if refs is None:
        return [], [
            {
                "kind": "refs",
                "reason": "local and remote-tracking refs could not be enumerated",
                "safe_action": "verify_local_refs",
            }
        ]

    candidates = _ref_candidates(refs, target_branch=target_branch, target_head=target_head)
    comparisons: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for candidate in candidates:
        comparison = _compare_ref(root, target_head=target_head, candidate=candidate)
        if comparison.get("disposition") == "ambiguous":
            ambiguous.append(comparison)
        else:
            comparisons.append(comparison)
    return comparisons, ambiguous


def _ref_candidates(
    lines: list[str], *, target_branch: str, target_head: str
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for line in lines:
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        full_name, name, head, symbolic_target = parts
        if not name or not head or symbolic_target or name.endswith("/HEAD"):
            continue
        if name == target_branch and head == target_head:
            continue
        source = "remote_tracking" if full_name.startswith("refs/remotes/") else "local"
        existing = grouped.get(head)
        if existing is None or (existing["source"] == "remote_tracking" and source == "local"):
            aliases = [] if existing is None else [str(existing["ref"]), *existing["aliases"]]
            grouped[head] = {
                "ref": name,
                "head": head,
                "source": source,
                "aliases": aliases,
            }
        else:
            existing["aliases"].append(name)
    return sorted(grouped.values(), key=lambda item: (str(item["source"]), str(item["ref"])))


def _compare_ref(root: Path, *, target_head: str, candidate: dict[str, Any]) -> dict[str, Any]:
    head = str(candidate["head"])
    unique_commits = _git_count(root, "rev-list", "--count", f"{target_head}..{head}")
    if unique_commits is None:
        return {
            **candidate,
            "kind": "branch",
            "disposition": "ambiguous",
            "reason": "branch ancestry could not be compared with the canonical target",
            "safe_action": "verify_branch_ancestry",
        }
    if unique_commits == 0:
        return {
            **candidate,
            "kind": "branch",
            "unique_commits": 0,
            "unique_patches": 0,
            "disposition": "merged",
        }

    cherry = _git_lines(root, "cherry", target_head, head)
    if cherry is None:
        return {
            **candidate,
            "kind": "branch",
            "unique_commits": unique_commits,
            "disposition": "ambiguous",
            "reason": "branch patch equivalence could not be determined",
            "safe_action": "verify_patch_equivalence",
        }
    unique_patches = sum(1 for line in cherry if line.startswith("+"))
    return {
        **candidate,
        "kind": "branch",
        "unique_commits": unique_commits,
        "unique_patches": unique_patches,
        "disposition": "unfolded" if unique_patches else "patch_equivalent",
        "safe_action": "review_and_fold_branch" if unique_patches else "verify_and_prune_branch",
    }


def _detached_head_gaps(
    repository: dict[str, Any], root: Path, target_head: str
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for checkout in _objects(repository.get("checkouts")):
        head = _text(checkout.get("head"))
        if (
            checkout.get("detached") is not True
            or not head
            or head == target_head
            or head in seen
            or checkout.get("prunable") is True
        ):
            continue
        seen.add(head)
        unique_commits = _git_count(root, "rev-list", "--count", f"{target_head}..{head}")
        if unique_commits == 0:
            continue
        reason = (
            "detached worktree commit ancestry could not be compared"
            if unique_commits is None
            else "detached worktree contains commits outside the canonical target"
        )
        gaps.append(
            {
                "kind": "detached_head",
                "checkout_id": checkout.get("checkout_id"),
                "head": head,
                "unique_commits": unique_commits,
                "reason": reason,
                "safe_action": "review_detached_worktree",
            }
        )
    return gaps


def _dirty_worktrees(repository: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for checkout in _objects(repository.get("checkouts")):
        if (
            checkout.get("dirty") is not True
            or checkout.get("exists") is not True
            or checkout.get("prunable") is True
        ):
            continue
        fingerprint = _object(checkout.get("fingerprint"))
        items.append(
            {
                "kind": "dirty_worktree",
                "checkout_id": checkout.get("checkout_id"),
                "branch": checkout.get("branch"),
                "head": checkout.get("head"),
                "detached": checkout.get("detached") is True,
                "status_hash": fingerprint.get("status_hash"),
                "safe_action": "commit_or_discard_worktree_changes",
            }
        )
    return sorted(items, key=lambda item: str(item.get("checkout_id", "")))


def _coverage_status(
    *,
    target_status: str,
    unfolded: list[dict[str, Any]],
    dirty_worktrees: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    disposition_errors: list[dict[str, Any]],
) -> str:
    if target_status == "stale":
        return "stale_target"
    if target_status != "ready" or ambiguous or disposition_errors:
        return "blocked_ambiguous"
    if unfolded or dirty_worktrees:
        return "incomplete_unfolded"
    return "complete"


def _safe_action(status: str) -> str:
    return {
        "complete": "none",
        "incomplete_unfolded": "review_and_fold_outstanding_work",
        "blocked_ambiguous": "resolve_ambiguous_git_state",
        "stale_target": "refresh_and_reconcile_target",
    }[status]


def _count_dispositions(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        disposition = str(item.get("disposition", "unknown"))
        counts[disposition] = counts.get(disposition, 0) + 1
    return dict(sorted(counts.items()))


def _command_root(repository: dict[str, Any], target: dict[str, Any]) -> Path | None:
    checkout_id = target.get("checkout_id")
    checkouts = _objects(repository.get("checkouts"))
    ordered = sorted(checkouts, key=lambda item: item.get("checkout_id") != checkout_id)
    for checkout in ordered:
        raw_path = checkout.get("path")
        if checkout.get("exists") is True and isinstance(raw_path, str) and raw_path:
            return Path(raw_path)
    primary = repository.get("primary_path")
    return Path(primary) if isinstance(primary, str) and primary else None


def _git_count(root: Path, *args: str) -> int | None:
    lines = _git_lines(root, *args)
    if lines is None or len(lines) != 1:
        return None
    try:
        return int(lines[0])
    except ValueError:
        return None


def _git_lines(root: Path, *args: str) -> list[str] | None:
    try:
        result = run_command(["git", *args], cwd=root, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.get("returncode") != 0:
        return None
    stdout = result.get("stdout")
    return str(stdout).splitlines() if isinstance(stdout, str) else []


def _object(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    raw_items = cast(list[object], value)
    return [cast(dict[str, Any], item) for item in raw_items if isinstance(item, dict)]


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
