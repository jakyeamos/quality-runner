from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import (
    FLEET_STANDARD_REPORT_SCHEMA,
    digest,
    standard_dimensions,
)
from quality_runner.fleet.matrix_maintenance import assess_matrix_maintenance


def matrix_maintenance_finding_arguments(
    *, repository: dict[str, Any], documents: dict[str, str], as_of: str
) -> dict[str, Any]:
    assessment = assess_matrix_maintenance(
        Path(str(repository["primary_path"])).expanduser().resolve(),
        documents,
        as_of,
    )
    dimension = "matrix_maintenance"
    return {
        "repository": repository,
        "dimension": dimension,
        "score": assessment["score"],
        "as_of": as_of,
        "status": assessment["status"],
        "severity": "observation",
        "priority": "P1",
        "confidence": "high" if assessment["status"] != "unknown" else "medium",
        "message": assessment["message"],
        "evidence": assessment["evidence"],
        "validation_commands": ["qr fleet audit run --all --standard matrix-maintenance --json"],
    }


def long_running_task_finding_arguments(
    *,
    repository: dict[str, Any],
    dimension: str,
    assessments: dict[str, dict[str, Any]],
    as_of: str,
) -> dict[str, Any]:
    assessment = assessments[dimension]
    return {
        "repository": repository,
        "dimension": dimension,
        "score": assessment["score"],
        "as_of": as_of,
        "status": assessment["status"],
        "severity": "observation",
        "priority": "P2",
        "confidence": "high",
        "message": assessment["message"],
        "evidence": assessment["evidence"],
        "applicability": assessment["applicability"],
        "validation_commands": [
            "qr fleet audit run --all --standard long-running-tasks --json"
        ],
    }


def build_standard_report(
    *,
    audit_id: str,
    as_of: str,
    projects_root: Path,
    scope: str,
    repositories: list[dict[str, Any]],
    standard: str,
) -> dict[str, Any]:
    dimensions = standard_dimensions(standard)
    assert dimensions
    rows: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    score_counts: dict[str, int] = {}
    for result in sorted(repositories, key=lambda item: str(item.get("repo_id", ""))):
        repository_path = _repository_path(result, projects_root)
        assessments = []
        for dimension in dimensions:
            finding = next(
                (
                    item
                    for item in result.get("findings", [])
                    if isinstance(item, dict) and item.get("dimension") == dimension
                ),
                None,
            )
            if finding is None:
                assessment = {
                    "dimension": dimension,
                    "status": "unknown",
                    "score": None,
                    "message": "The selected standard produced no finding for this dimension.",
                    "evidence": [],
                }
            else:
                assessment = {
                    "dimension": dimension,
                    "status": str(finding.get("status", "unknown")),
                    "score": finding.get("score"),
                    "message": str(finding.get("message", "")),
                    "evidence": [
                        item for item in finding.get("evidence", []) if isinstance(item, dict)
                    ][:12],
                }
            status = str(assessment["status"])
            score = assessment["score"]
            status_counts[status] = status_counts.get(status, 0) + 1
            score_key = "not_applicable" if score is None else str(score)
            score_counts[score_key] = score_counts.get(score_key, 0) + 1
            assessments.append(assessment)
        row = {
            "repo_id": result.get("repo_id"),
            "repository_path": repository_path,
            "assessments": assessments,
        }
        if len(assessments) == 1:
            row.update({key: assessments[0][key] for key in ("status", "score", "message", "evidence")})
        rows.append(row)
    report = {
        "schema": FLEET_STANDARD_REPORT_SCHEMA,
        "status": "completed" if repositories else "blocked",
        "standard": standard,
        "dimensions": list(dimensions),
        "audit_id": audit_id,
        "as_of": as_of,
        "projects_root": str(projects_root),
        "scope": scope,
        "repository_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "score_counts": dict(sorted(score_counts.items())),
        "repositories": rows,
        "privacy": {
            "private_local_report": True,
            "raw_code": False,
            "raw_diffs": False,
            "credentials": False,
        },
    }
    if len(dimensions) == 1:
        report["dimension"] = dimensions[0]
    report["provenance_hash"] = digest(report)
    return report


def _repository_path(result: dict[str, Any], projects_root: Path) -> str | None:
    repository = result.get("repository")
    if not isinstance(repository, dict) or not isinstance(repository.get("primary_path"), str):
        return None
    primary_path = Path(repository["primary_path"]).expanduser().resolve()
    try:
        return primary_path.relative_to(projects_root.expanduser().resolve()).as_posix()
    except ValueError:
        return None
