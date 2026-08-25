from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quality_runner.fleet.audit_coverage import AUDIT_COVERAGE_STATUSES


class AuditCoverageFeedError(ValueError):
    """Raised when feed coverage metadata is internally inconsistent."""


def project_audit_coverage(value: object) -> dict[str, Any]:
    coverage = _object(value)
    allowed = (
        "schema",
        "status",
        "canonical_branch",
        "canonical_head",
        "evidence_scope",
        "canonical_findings_valid",
        "comparison_eligible",
        "publication_ready",
        "unfolded_branch_count",
        "dirty_worktree_count",
        "ambiguous_item_count",
        "excluded_ref_count",
        "unfolded_branches",
        "dirty_worktrees",
        "ambiguous_items",
        "excluded_ref_counts",
        "observed_unfolded_branch_count",
        "observed_dirty_worktree_count",
        "observed_ambiguous_item_count",
        "custody_dispositioned_count",
        "custody_dispositioned_items",
        "custody_disposition_errors",
        "safe_action",
        "provenance_hash",
    )
    return {key: coverage.get(key) for key in allowed if key in coverage}


def validate_feed_audit_coverage(
    feed: Mapping[str, Any], repositories: list[dict[str, Any]]
) -> None:
    aggregate = _object(feed.get("audit_coverage"))
    repository_coverage = [_object(repository.get("audit_coverage")) for repository in repositories]
    if not aggregate and not any(repository_coverage):
        return
    if not aggregate or not all(repository_coverage):
        raise AuditCoverageFeedError("maturity feed audit coverage is only partially present")
    policy = str(aggregate.get("policy", ""))
    if policy not in {"require_complete", "allow_incomplete"}:
        raise AuditCoverageFeedError("maturity feed audit coverage policy is invalid")
    statuses = [str(coverage.get("status", "")) for coverage in repository_coverage]
    if any(status not in AUDIT_COVERAGE_STATUSES for status in statuses):
        raise AuditCoverageFeedError("maturity feed repository audit coverage is incomplete")
    incomplete = sum(status != "complete" for status in statuses)
    complete = len(statuses) - incomplete
    if aggregate.get("complete_repository_count") != complete:
        raise AuditCoverageFeedError(
            "maturity feed complete coverage count does not match repositories"
        )
    if aggregate.get("incomplete_repository_count") != incomplete:
        raise AuditCoverageFeedError(
            "maturity feed incomplete coverage count does not match repositories"
        )
    if aggregate.get("comparison_eligible") != (incomplete == 0):
        raise AuditCoverageFeedError("maturity feed comparison eligibility is inconsistent")
    expected_status = "complete" if incomplete == 0 else "incomplete"
    if aggregate.get("status") != expected_status:
        raise AuditCoverageFeedError("maturity feed audit coverage status is inconsistent")
    if incomplete and policy != "allow_incomplete":
        raise AuditCoverageFeedError("incomplete audit coverage requires an explicit feed policy")


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
