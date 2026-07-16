from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

LIFECYCLE_STATUSES = {
    "audit-clean",
    "gates-clean",
    "merge-ready",
    "blocked",
    "failed",
    "workflow-timeout",
    "needs-triage",
}
MAX_CI_PROVENANCE_AGE = timedelta(hours=24)


def compute_lifecycle_status(
    *,
    summary_status: str,
    handoff_status: str | None,
    gate_verification: dict[str, Any],
    audit: dict[str, Any],
    repo_scan: dict[str, Any] | None = None,
) -> str:
    failure_type = _string_or_none(gate_verification.get("failure_type"))
    if (
        failure_type == "workflow-timeout"
        or summary_status == "blocked"
        and failure_type == "workflow-timeout"
    ):
        return "workflow-timeout"

    gate_status = _string_or_none(gate_verification.get("status"))
    audit_status = _string_or_none(audit.get("status"))

    if handoff_status == "gates-failed" or gate_status == "failed" or summary_status == "failed":
        return "failed"

    if handoff_status == "review-required":
        return "blocked"

    readiness = gate_verification.get("readiness")
    if isinstance(readiness, dict) and readiness.get("status") == "blocked":
        return "blocked"

    if handoff_status == "gates-blocked" or gate_status == "blocked" or summary_status == "blocked":
        return "blocked"

    if _merge_ready(
        gate_status=gate_status,
        handoff_status=handoff_status,
        repo_scan=repo_scan,
        gate_verification=gate_verification,
    ):
        return "merge-ready"

    if gate_status in {"passed", "passed-with-findings"} and _ci_provenance_blocked(repo_scan):
        return "blocked"

    if handoff_status == "gates-clean" or (
        gate_status in {"passed", "passed-with-findings"}
        and summary_status in {"passed", "passed-with-findings"}
    ):
        return "gates-clean"

    if audit_status == "clean" and gate_status in {None, ""}:
        return "audit-clean"

    if audit_status == "clean" and summary_status == "clean":
        return "audit-clean"

    return "needs-triage"


def _merge_ready(
    *,
    gate_status: str | None,
    handoff_status: str | None,
    repo_scan: dict[str, Any] | None,
    gate_verification: dict[str, Any],
) -> bool:
    if handoff_status != "gates-clean" and gate_status not in {"passed", "passed-with-findings"}:
        return False
    if gate_status not in {"passed", "passed-with-findings"}:
        return False
    readiness = gate_verification.get("readiness")
    if isinstance(readiness, dict) and readiness.get("status") not in {"passed", "not-applicable"}:
        return False
    return not _ci_provenance_blocked(repo_scan)


def _ci_provenance_blocked(repo_scan: dict[str, Any] | None) -> bool:
    if not isinstance(repo_scan, dict):
        return True
    checks = repo_scan.get("ci_checks")
    if not isinstance(checks, list) or not checks:
        return True
    provenance_value = repo_scan.get("git_provenance") or repo_scan.get("provenance")
    git_provenance = provenance_value if isinstance(provenance_value, dict) else {}
    current_head = git_provenance.get("head_sha")
    current_branch = git_provenance.get("branch")
    if not isinstance(current_head, str) or not current_head:
        return True
    if not isinstance(current_branch, str) or not current_branch:
        return True
    for check in checks:
        if not isinstance(check, dict) or check.get("conclusion") != "success":
            return True
        if check.get("head_sha") != current_head:
            return True
        check_ref = check.get("ref")
        valid_refs = {current_branch, f"refs/heads/{current_branch}"}
        if not isinstance(check_ref, str) or not check_ref or check_ref not in valid_refs:
            return True
        if not check.get("workflow_run_id") or not check.get("captured_at"):
            return True
        if not _fresh_capture(check.get("captured_at")):
            return True
    return False


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _fresh_capture(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        captured = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if captured.tzinfo is None:
        return False
    now = datetime.now(UTC)
    return captured <= now + timedelta(minutes=5) and now - captured <= MAX_CI_PROVENANCE_AGE
