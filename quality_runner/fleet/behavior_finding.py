from __future__ import annotations

from typing import Any


def behavior_finding_arguments(
    repository: dict[str, Any], assessment: dict[str, Any], as_of: str
) -> dict[str, Any]:
    ready = bool(assessment["release_ready"])
    status = (
        "not_applicable"
        if assessment["applicability"] == "not_applicable"
        else "maintained"
        if ready
        else "blocked"
        if assessment["result_status"] == "blocked"
        else "unknown"
    )
    return {
        "repository": repository,
        "dimension": "behavior_assurance",
        "score": assessment["score"],
        "as_of": as_of,
        "status": status,
        "severity": "observation" if ready else "high",
        "priority": "P2" if ready else "P0",
        "confidence": "high",
        "message": assessment.get(
            "detail", "Behavior assurance has unresolved contract or receipt gaps."
        ),
        "evidence": [
            {
                "path": str(assessment["contract_path"]),
                "detail": str(assessment["contract_status"]),
            },
            *[
                {
                    "path": str(assessment["receipt_directory"]),
                    "detail": str(gap.get("message", "Behavior assurance gap")),
                }
                for gap in assessment["gaps"][:15]
            ],
        ],
        "validation_commands": ["qr fleet audit run --repo-path REPO --json"],
    }
