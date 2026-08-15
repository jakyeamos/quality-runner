from __future__ import annotations

from typing import Any

from quality_runner.fleet.contracts import DIMENSION_LABELS, FLEET_FINDING_SCHEMA, digest


def finding(
    *,
    repository: dict[str, Any],
    dimension: str,
    score: int | None,
    as_of: str,
    status: str,
    severity: str,
    priority: str,
    confidence: str,
    message: str,
    evidence: list[dict[str, str]],
    validation_commands: list[str],
    applicability: str | None = None,
    confirmed_critical_risk: bool = False,
) -> dict[str, Any]:
    resolved_applicability = applicability or (
        "not_applicable" if status == "not_applicable" else "applicable"
    )
    return {
        "schema": FLEET_FINDING_SCHEMA,
        "finding_id": digest([repository["repo_id"], dimension, status, evidence])[:16],
        "repo_id": repository["repo_id"],
        "as_of": as_of,
        "dimension": dimension,
        "label": DIMENSION_LABELS[dimension],
        "applicable": (
            False
            if resolved_applicability == "not_applicable"
            else True
            if resolved_applicability == "applicable"
            else None
        ),
        "applicability": resolved_applicability,
        "confirmed_critical_risk": confirmed_critical_risk,
        "score": score,
        "status": status,
        "severity": severity,
        "priority": priority,
        "confidence": confidence,
        "message": message,
        "evidence": evidence,
        "validation_commands": validation_commands,
        "provenance_hash": digest(
            {"repo_id": repository["repo_id"], "dimension": dimension, "evidence": evidence}
        ),
    }


def validation_commands(dimension: str, scan: dict[str, Any]) -> list[str]:
    commands = [
        str(item.get("command"))
        for item in scan.get("quality_commands", [])
        if isinstance(item, dict) and isinstance(item.get("command"), str)
    ]
    if dimension == "quality_commands" and commands:
        return commands[:6]
    return ["qr audit REPO --profile environment-legibility --json"]
