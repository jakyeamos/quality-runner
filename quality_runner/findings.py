from __future__ import annotations

from typing import Any

from quality_runner.actionability import ACTIONABILITY_VALUES
from quality_runner.lifecycle_status import LIFECYCLE_STATUSES
from quality_runner.schema_constants import (
    AGENT_HANDOFF_SCHEMA,
    AUDIT_REPORT_SCHEMA,
    REMEDIATION_PLAN_SCHEMA,
)

ValidationResult = dict[str, Any]
ALLOWED_SEVERITIES = {"critical", "blocker", "warning", "observation"}
ALLOWED_PRIORITIES = {"high", "medium", "low"}
ALLOWED_HANDOFF_STATUSES = {
    "clean",
    "planned",
    "gates-discovered",
    "gates-executed",
    "gates-blocked",
    "gates-failed",
    "gates-clean",
}


def require_valid(name: str, result: ValidationResult) -> None:
    if result.get("passed") is True:
        return
    errors = result.get("errors")
    if isinstance(errors, list) and errors:
        message = "; ".join(str(error) for error in errors)
    else:
        message = "unknown validation error"
    raise ValueError(f"invalid {name}: {message}")


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
        actionability = finding.get("actionability")
        if actionability is not None and (
            not isinstance(actionability, str) or actionability not in ACTIONABILITY_VALUES
        ):
            errors.append(f"finding {finding_id} actionability is not in the allowed vocabulary")
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
        priority = slice_item.get("priority")
        if isinstance(priority, str) and priority and priority not in ALLOWED_PRIORITIES:
            errors.append(f"slice {slice_id} priority is not in the allowed vocabulary")
        if not _non_empty_finding_list(slice_item.get("findings")):
            errors.append(f"slice {slice_id} has no findings")
        if not _non_empty_string_list(slice_item.get("actions")):
            errors.append(f"slice {slice_id} has no actions")
        if not _non_empty_string_list(slice_item.get("verification_gates")):
            errors.append(f"slice {slice_id} has no verification gates")
        if slice_item.get("action_groups") is not None and not _optional_action_group_list(
            slice_item.get("action_groups")
        ):
            errors.append(f"slice {slice_id} action_groups must be a list of action groups")
    return {"passed": not errors, "errors": errors}


def validate_agent_handoff(handoff: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    if handoff.get("schema") != AGENT_HANDOFF_SCHEMA:
        errors.append(f"agent handoff schema must be {AGENT_HANDOFF_SCHEMA}")

    status = handoff.get("status")
    if not _non_empty_string(status):
        errors.append("agent handoff status must be a non-empty string")
    elif status not in ALLOWED_HANDOFF_STATUSES:
        errors.append("agent handoff status is not in the allowed vocabulary")

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

    gate_verification = handoff.get("gate_verification")
    if gate_verification is not None and not _gate_verification_summary(gate_verification):
        errors.append("agent handoff gate_verification must be a gate verification summary object")

    lifecycle_status = handoff.get("lifecycle_status")
    if lifecycle_status is not None and (
        not isinstance(lifecycle_status, str) or lifecycle_status not in LIFECYCLE_STATUSES
    ):
        errors.append("agent handoff lifecycle_status is not in the allowed vocabulary")

    intent = handoff.get("intent")
    if intent is not None and not isinstance(intent, dict):
        errors.append("agent handoff intent must be an object when present")

    next_slice = handoff.get("next_slice")
    if status in {"clean", "gates-clean"}:
        if next_slice is not None:
            errors.append("agent handoff next_slice must be null for clean status")
    elif (
        status in {"planned", "gates-discovered", "gates-executed", "gates-blocked", "gates-failed"}
        and next_slice is not None
    ):
        if not _slice_item(next_slice):
            errors.append("agent handoff next_slice must be a remediation slice object")
    elif status in {"planned", "gates-blocked", "gates-failed"} and next_slice is None:
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
        and value.get("priority") in ALLOWED_PRIORITIES
        and _non_empty_finding_list(value.get("findings"))
        and _non_empty_string_list(value.get("actions"))
        and _optional_action_group_list(value.get("action_groups"))
        and _non_empty_string_list(value.get("verification_gates"))
    )


def _gate_verification_summary(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        _non_empty_string(value.get("status"))
        and _non_empty_string(value.get("recommended_classification"))
        and isinstance(value.get("blockers"), list)
        and all(_gate_blocker(item) for item in value["blockers"])
    )


def _gate_blocker(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return _non_empty_string(value.get("id")) and _non_empty_string(value.get("status"))


def _optional_action_group_list(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, list) and all(_action_group(item) for item in value)


def _action_group(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        _non_empty_string(value.get("class"))
        and (
            _non_empty_string_list(value.get("gate_ids"))
            or _non_empty_string_list(value.get("finding_ids"))
        )
        and _non_empty_string_list(value.get("actions"))
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
