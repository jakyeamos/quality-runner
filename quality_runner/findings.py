from __future__ import annotations

from typing import Any

ValidationResult = dict[str, Any]
AUDIT_REPORT_SCHEMA = "quality-runner-audit-report-v0.1"
REMEDIATION_PLAN_SCHEMA = "quality-runner-remediation-plan-v0.1"


def validate_audit_report(report: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    findings = report.get("findings")
    if not isinstance(findings, list):
        return {"passed": False, "errors": ["audit report findings must be a list"]}

    if report.get("schema") != AUDIT_REPORT_SCHEMA and _all_dict_items(findings):
        errors.append(f"audit report schema must be {AUDIT_REPORT_SCHEMA}")

    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"finding at index {index} is not an object")
            continue
        for field in ("id", "severity", "category", "summary", "recommended_fix"):
            if not _non_empty_string(finding.get(field)):
                errors.append(f"finding at index {index} field {field} must be a non-empty string")
        finding_id = str(finding.get("id", "unknown"))
        evidence = finding.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"finding {finding_id} has no evidence")
        verification = finding.get("verification")
        if not isinstance(verification, list) or not verification:
            errors.append(f"finding {finding_id} has no verification")
    return {"passed": not errors, "errors": errors}


def validate_remediation_plan(plan: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    slices = plan.get("slices")
    if not isinstance(slices, list):
        return {"passed": False, "errors": ["remediation plan slices must be a list"]}

    if plan.get("schema") != REMEDIATION_PLAN_SCHEMA and _all_dict_items(slices):
        errors.append(f"remediation plan schema must be {REMEDIATION_PLAN_SCHEMA}")

    for index, slice_item in enumerate(slices):
        if not isinstance(slice_item, dict):
            errors.append(f"slice at index {index} is not an object")
            continue
        for field in ("id", "title"):
            if not _non_empty_string(slice_item.get(field)):
                errors.append(f"slice at index {index} field {field} must be a non-empty string")
        slice_id = str(slice_item.get("id", "unknown"))
        findings = slice_item.get("findings")
        if not isinstance(findings, list) or not findings:
            errors.append(f"slice {slice_id} has no findings")
        verification = slice_item.get("verification")
        if not isinstance(verification, list) or not verification:
            errors.append(f"slice {slice_id} has no verification")
    return {"passed": not errors, "errors": errors}


def _all_dict_items(items: list[Any]) -> bool:
    return all(isinstance(item, dict) for item in items)


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)
