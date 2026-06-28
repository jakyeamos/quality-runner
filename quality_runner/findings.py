from __future__ import annotations

from typing import Any

ValidationResult = dict[str, Any]


def validate_audit_report(report: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    for finding in _dict_items(report.get("findings")):
        finding_id = str(finding.get("id", "unknown"))
        evidence = finding.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"finding {finding_id} has no evidence")
    return {"passed": not errors, "errors": errors}


def validate_remediation_plan(plan: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    for slice_item in _dict_items(plan.get("slices")):
        slice_id = str(slice_item.get("id", "unknown"))
        verification = slice_item.get("verification")
        if not isinstance(verification, list) or not verification:
            errors.append(f"slice {slice_id} has no verification")
    return {"passed": not errors, "errors": errors}


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
