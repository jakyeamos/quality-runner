from __future__ import annotations

from typing import Any

ValidationResult = dict[str, Any]
AUDIT_REPORT_SCHEMA = "quality-runner-audit-report-v0.1"
REMEDIATION_PLAN_SCHEMA = "quality-runner-remediation-plan-v0.1"


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
        for field in ("id", "title"):
            if not _non_empty_string(slice_item.get(field)):
                errors.append(f"slice at index {index} field {field} must be a non-empty string")
        slice_id = str(slice_item.get("id", "unknown"))
        findings = slice_item.get("findings")
        if not _non_empty_string_list(findings):
            errors.append(f"slice {slice_id} has no findings")
        verification = slice_item.get("verification")
        if not _non_empty_string_list(verification):
            errors.append(f"slice {slice_id} has no verification")
    return {"passed": not errors, "errors": errors}


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _non_empty_string_list(value: object) -> bool:
    return (
        isinstance(value, list) and bool(value) and all(_non_empty_string(item) for item in value)
    )
