from __future__ import annotations

from typing import Any

ValidationResult = dict[str, Any]
AUDIT_REPORT_SCHEMA = "quality-runner-audit-report-v0.1"
REMEDIATION_PLAN_SCHEMA = "quality-runner-remediation-plan-v0.1"
AGENT_HANDOFF_SCHEMA = "quality-runner-agent-handoff-v0.1"
ALLOWED_SEVERITIES = {"blocker", "warning", "observation"}


def validate_audit_report(report: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    if report.get("schema") != AUDIT_REPORT_SCHEMA:
        errors.append(f"audit report schema must be {AUDIT_REPORT_SCHEMA}")

    findings = report.get("findings")
    if not isinstance(findings, list):
        errors.append("audit report findings must be a list")
        return {"passed": False, "errors": errors}

    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"finding at index {index} is not an object")
            continue
        for field in ("id", "severity", "category", "summary", "recommended_fix"):
            if not _non_empty_string(finding.get(field)):
                errors.append(f"finding at index {index} field {field} must be a non-empty string")
        finding_id = str(finding.get("id", "unknown"))
        severity = finding.get("severity")
        if isinstance(severity, str) and severity and severity not in ALLOWED_SEVERITIES:
            errors.append(f"finding {finding_id} severity is not in the allowed vocabulary")
        evidence = finding.get("evidence")
        if not _non_empty_string_list(evidence):
            errors.append(f"finding {finding_id} has no evidence")
        verification = finding.get("verification")
        if not _non_empty_string_list(verification):
            errors.append(f"finding {finding_id} has no verification")
    return {"passed": not errors, "errors": errors}


def validate_remediation_plan(plan: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    if plan.get("schema") != REMEDIATION_PLAN_SCHEMA:
        errors.append(f"remediation plan schema must be {REMEDIATION_PLAN_SCHEMA}")

    slices = plan.get("slices")
    if not isinstance(slices, list):
        errors.append("remediation plan slices must be a list")
        return {"passed": False, "errors": errors}

    for index, slice_item in enumerate(slices):
        if not isinstance(slice_item, dict):
            errors.append(f"slice at index {index} is not an object")
            continue
        for field in ("id", "title", "priority"):
            if not _non_empty_string(slice_item.get(field)):
                errors.append(f"slice at index {index} field {field} must be a non-empty string")
        slice_id = str(slice_item.get("id", "unknown"))
        if not _non_empty_finding_list(slice_item.get("findings")):
            errors.append(f"slice {slice_id} has no findings")
        if not _non_empty_string_list(slice_item.get("actions")):
            errors.append(f"slice {slice_id} has no actions")
        if not _non_empty_string_list(slice_item.get("verification_gates")):
            errors.append(f"slice {slice_id} has no verification gates")
    return {"passed": not errors, "errors": errors}


def validate_agent_handoff(handoff: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    if handoff.get("schema") != AGENT_HANDOFF_SCHEMA:
        errors.append(f"agent handoff schema must be {AGENT_HANDOFF_SCHEMA}")

    if not _non_empty_string(handoff.get("status")):
        errors.append("agent handoff status must be a non-empty string")

    if handoff.get("implementation_allowed") is not False:
        errors.append("agent handoff implementation_allowed must be false")

    artifact_paths = handoff.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        errors.append("agent handoff artifact_paths must be an object")
    elif not all(
        _non_empty_string(key) and _non_empty_string(value) for key, value in artifact_paths.items()
    ):
        errors.append("agent handoff artifact_paths must contain string paths")

    if not _warning_list(handoff.get("warnings")):
        errors.append("agent handoff warnings must be a list of warning objects")

    if not _string_list(handoff.get("finding_ids")):
        errors.append("agent handoff finding_ids must be a string list")

    if not _string_list(handoff.get("slice_ids")):
        errors.append("agent handoff slice_ids must be a string list")

    status = handoff.get("status")
    next_slice = handoff.get("next_slice")
    if status == "clean":
        if next_slice is not None:
            errors.append("agent handoff next_slice must be null for clean status")
    elif not _slice_item(next_slice):
        errors.append("agent handoff next_slice must be a remediation slice object")

    if not _string_list(handoff.get("verification_gates")):
        errors.append("agent handoff verification_gates must be a string list")

    return {"passed": not errors, "errors": errors}


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_empty_string_list(value: object) -> bool:
    return (
        isinstance(value, list) and bool(value) and all(_non_empty_string(item) for item in value)
    )


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _non_empty_finding_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(_finding_item(item) for item in value)


def _finding_item(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        all(
            _non_empty_string(value.get(field))
            for field in ("id", "severity", "category", "summary")
        )
        and value.get("severity") in ALLOWED_SEVERITIES
    )


def _slice_item(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        all(_non_empty_string(value.get(field)) for field in ("id", "title", "priority"))
        and _non_empty_finding_list(value.get("findings"))
        and _non_empty_string_list(value.get("actions"))
        and _non_empty_string_list(value.get("verification_gates"))
    )


def _warning_list(value: object) -> bool:
    if not isinstance(value, list):
        return False
    return all(
        isinstance(item, dict)
        and _non_empty_string(item.get("code"))
        and _non_empty_string(item.get("message"))
        and _non_empty_string(item.get("path"))
        for item in value
    )
