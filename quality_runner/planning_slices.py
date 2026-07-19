from __future__ import annotations

from typing import Any

from quality_runner.verification_contract import verification_contract_fields

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def slice_for_finding(finding: dict[str, Any]) -> dict[str, Any]:
    finding_id = finding["id"]
    recommended_fix = finding["recommended_fix"]
    verification_contract = verification_contract_fields(
        finding,
        explicit_mode=finding.get("verification_mode"),
    )
    slice_item = {
        "id": f"remediate-{finding_id}",
        "title": f"Remediate {finding_id}",
        "priority": priority_for_finding(finding),
        "findings": [
            {
                "id": finding_id,
                "severity": finding["severity"],
                "category": finding["category"],
                "summary": finding["summary"],
                **_optional_actionability(finding),
                **_optional_disposition(finding),
                **verification_contract,
            }
        ],
        "actions": [
            f"Apply recommended fix: {recommended_fix}",
            f"Rerun quality-runner and confirm {finding_id} no longer appears.",
        ],
        "verification_gates": list(finding["verification"]),
        **verification_contract,
    }
    score = finding.get("score")
    if isinstance(score, int):
        slice_item["score"] = score
    for field in ("impact", "effort", "fix_risk", "confidence", "why_now", "leverage"):
        value = finding.get(field)
        if value is not None:
            slice_item[field] = value
    return slice_item


def slice_sort_key(slice_item: dict[str, Any]) -> tuple[int, int, float, int, str]:
    findings = slice_item.get("findings")
    category = None
    if isinstance(findings, list) and findings and isinstance(findings[0], dict):
        category = findings[0].get("category")
    security_rank = 0 if isinstance(category, str) and category.startswith("security:") else 1
    priority = str(slice_item.get("priority") or "")
    score = slice_item.get("score")
    ranking_score = score if isinstance(score, int) else 0
    leverage_rank = 0.0
    leverage = slice_item.get("leverage")
    if isinstance(leverage, dict):
        rank = leverage.get("rank")
        if isinstance(rank, (int, float)):
            leverage_rank = float(rank)
    return (
        security_rank,
        PRIORITY_ORDER.get(priority, 99),
        -leverage_rank,
        -ranking_score,
        str(slice_item.get("id") or ""),
    )


def priority_for_finding(finding: dict[str, Any]) -> str:
    category = finding.get("category")
    severity = finding["severity"]
    if isinstance(category, str) and category.startswith("security:"):
        if severity in {"critical", "blocker"}:
            return "high"
        if category.startswith("security:agent-review"):
            return "medium"
        if severity == "warning":
            return "medium"
    if severity == "blocker":
        return "high"
    if severity == "warning":
        return "medium"
    return "low"


def finding_sort_key(finding: dict[str, Any]) -> tuple[int, int, int, str]:
    category = finding.get("category")
    security_rank = 0 if isinstance(category, str) and category.startswith("security:") else 1
    priority = priority_for_finding(finding)
    score = finding.get("score")
    ranking_score = score if isinstance(score, int) else 0
    return security_rank, PRIORITY_ORDER.get(priority, 99), -ranking_score, finding["id"]


def _optional_actionability(finding: dict[str, Any]) -> dict[str, str]:
    actionability = finding.get("actionability")
    rationale = finding.get("actionability_rationale")
    if not isinstance(actionability, str) or not actionability:
        return {}
    payload: dict[str, str] = {"actionability": actionability}
    if isinstance(rationale, str) and rationale:
        payload["actionability_rationale"] = rationale
    return payload


def _optional_disposition(finding: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in (
        "disposition_class",
        "disposition_group",
        "disposition_required",
        "owner_role",
        "disposition_rationale",
    ):
        if key in finding and finding[key] is not None:
            payload[key] = finding[key]
    return payload
