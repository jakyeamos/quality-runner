from __future__ import annotations

from typing import Any

from quality_runner.fleet.contracts import DIMENSION_LABELS, FLEET_PLAN_SCHEMA, digest
from quality_runner.fleet.legibility_support import plan_confidence
from quality_runner.fleet.projection import build_local_projection


def build_remediation_plan(
    *,
    repository: dict[str, Any],
    findings: list[dict[str, Any]],
    scan: dict[str, Any],
    as_of: str,
) -> dict[str, Any]:
    tasks: dict[str, list[dict[str, Any]]] = {"P0": [], "P1": [], "P2": []}
    for finding in findings:
        if finding.get("status") == "not_applicable" or finding.get("score") == 4:
            continue
        priority = str(finding.get("priority", "P1"))
        if priority not in tasks:
            priority = "P1"
        dimension = str(finding.get("dimension", "environment"))
        tasks[priority].append(
            {
                "task_id": f"{repository['repo_id']}-{dimension}",
                "dimension": dimension,
                "observed_gap": finding.get("message"),
                "evidence": finding.get("evidence", []),
                "exact_surface": [item.get("path") for item in finding.get("evidence", [])],
                "owner": "repository-owner",
                "dependencies": ["preserve existing repository conventions"],
                "validation_commands": finding.get("validation_commands", []),
                "acceptance_criteria": [
                    f"{DIMENSION_LABELS.get(dimension, dimension)} is discoverable, validated, and fresh",
                    "QR replay records the evidence without modifying the source checkout",
                ],
                "rollback_or_removal": "Remove the local projection or revert the documentation-only commit if it conflicts with the repository contract.",
            }
        )
    projection = build_local_projection(repository, findings)
    return {
        "schema": FLEET_PLAN_SCHEMA,
        "plan_id": digest([repository["repo_id"], findings])[:16],
        "repo_id": repository["repo_id"],
        "as_of": as_of,
        "status": "ready" if any(tasks.values()) else "complete",
        "observed_gap_summary": f"{sum(len(items) for items in tasks.values())} remediation task(s) remain below full maturity.",
        "impact": "Agents may spend more context, choose unverified commands, or make unsafe assumptions when the environment contract is incomplete.",
        "confidence": plan_confidence(findings),
        "affected_surfaces": sorted(
            {
                path
                for finding in findings
                for item in finding.get("evidence", [])
                for path in [item.get("path")]
                if isinstance(path, str)
            }
        ),
        "tasks": tasks,
        "owner": "repository-owner",
        "local_projection": projection,
        "unresolved_questions": [
            "Which repository-specific command should be the canonical pre-PR gate if several commands are discovered?",
        ],
        "provenance_hash": digest({"repo": repository, "scan": scan, "findings": findings}),
    }
