from __future__ import annotations

from typing import Any

ValidationResult = dict[str, Any]


def validate_audit_report(report: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    findings = report.get("findings")
    if not isinstance(findings, list):
        return {"passed": False, "errors": ["audit report findings must be a list"]}

    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"finding at index {index} is not an object")
            continue
        finding_id = str(finding.get("id", "unknown"))
        evidence = finding.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"finding {finding_id} has no evidence")
    return {"passed": not errors, "errors": errors}


def validate_remediation_plan(plan: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    slices = plan.get("slices")
    if not isinstance(slices, list):
        return {"passed": False, "errors": ["remediation plan slices must be a list"]}

    for index, slice_item in enumerate(slices):
        if not isinstance(slice_item, dict):
            errors.append(f"slice at index {index} is not an object")
            continue
        slice_id = str(slice_item.get("id", "unknown"))
        verification = slice_item.get("verification")
        if not isinstance(verification, list) or not verification:
            errors.append(f"slice {slice_id} has no verification")
    return {"passed": not errors, "errors": errors}
