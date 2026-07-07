from __future__ import annotations

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

    if handoff_status == "gates-blocked" or gate_status == "blocked" or summary_status == "blocked":
        return "blocked"

    if _merge_ready(gate_status=gate_status, handoff_status=handoff_status, repo_scan=repo_scan):
        return "merge-ready"

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
) -> bool:
    if handoff_status != "gates-clean" and gate_status not in {"passed", "passed-with-findings"}:
        return False
    if gate_status not in {"passed", "passed-with-findings"}:
        return False
    checks = repo_scan.get("ci_checks") if isinstance(repo_scan, dict) else None
    if not isinstance(checks, list) or not checks:
        return False
    for check in checks:
        if not isinstance(check, dict):
            continue
        conclusion = check.get("conclusion")
        if conclusion != "success":
            return False
    return True


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
