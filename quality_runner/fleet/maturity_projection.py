from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from quality_runner.fleet.agent_usability_scoring import applicable_agent_usability_scores
from quality_runner.fleet.cache_design import public_cache_design_projection
from quality_runner.fleet.maturity_coverage import project_audit_coverage
from quality_runner.fleet.quality_outcomes import classify_quality_outcome
from quality_runner.fleet.repository_maturity import build_repository_maturity

MAX_DIMENSION_GAPS = 64


class MaturityProjectionError(ValueError):
    """Raised when an audit row cannot become a maturity projection."""


def repository_projection(repository: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    repo_id = _required_string(repository, "repo_id")
    if _required_string(finding, "repo_id") != repo_id:
        raise MaturityProjectionError(f"repository and finding IDs do not match: {repo_id}")
    primary_path = _required_string(repository, "primary_path")
    target = _object(repository.get("target_branch"))
    audit_coverage = project_audit_coverage(repository.get("audit_coverage"))
    findings = _objects(finding.get("findings"))
    scores: dict[str, float | None] = {}
    gaps: list[Mapping[str, Any]] = []
    applicable_scores: list[float] = []
    statuses: list[str] = []
    dimension_statuses: dict[str, str] = {}
    dimension_applicability: dict[str, str] = {}
    critical_dimensions: list[str] = []
    blockers = 0
    non_dynamic_blockers = 0
    agent_attention = False
    cache_design: dict[str, Any] = {}

    for item in findings:
        dimension = _required_string(item, "dimension")
        status = str(item.get("status", "unknown"))
        statuses.append(status)
        dimension_statuses[dimension] = status
        applicability = _applicability(item, status)
        dimension_applicability[dimension] = applicability
        if dimension == "cache_design":
            assessment = next(
                (
                    evidence
                    for evidence in _objects(item.get("evidence"))
                    if evidence.get("schema") == "quality-runner-cache-design-assessment-v1"
                ),
                {},
            )
            if assessment:
                cache_design = public_cache_design_projection(assessment)
        raw_score = item.get("score")
        score = float(raw_score) if isinstance(raw_score, (int, float)) else None
        scores[dimension] = score if applicability != "not_applicable" else None
        if applicability == "applicable" and score is not None:
            applicable_scores.append(score)
        if applicability != "not_applicable" and (score is None or score < 4):
            gaps.append(_gap(dimension, status, score, str(item.get("message", ""))))
        if status == "blocked" or item.get("severity") == "blocker" or item.get("priority") == "P0":
            blockers += 1
            non_dynamic_blockers += dimension != "dynamic_verification"
        if item.get("confirmed_critical_risk") is True:
            critical_dimensions.append(dimension)

    agent_usability = _object(finding.get("agent_usability"))
    for item in applicable_agent_usability_scores(agent_usability):
        dimension, status, score = str(item["dimension"]), str(item["status"]), float(item["score"])
        scores[dimension] = score
        dimension_statuses[dimension] = status
        dimension_applicability[dimension] = "applicable"
        applicable_scores.append(score)
        if score < 4:
            agent_attention = True
            gaps.append(_gap(dimension, status, score, str(item["message"])))
        if status == "blocked":
            blockers += 1

    dynamic_status = str(_object(finding.get("dynamic")).get("status", "not_selected"))
    quality_status = _quality_status(blockers, dynamic_status, statuses, agent_attention)
    quality_outcome = classify_quality_outcome(
        dynamic_status=dynamic_status,
        non_dynamic_blockers=non_dynamic_blockers,
        statuses=statuses,
        healthy=quality_status == "healthy",
        dimension_gaps=gaps,
        blocker_count=blockers,
    )
    source_mean = (
        round(sum(applicable_scores) / len(applicable_scores), 3) if applicable_scores else None
    )
    model = build_repository_maturity(
        scores,
        dimension_statuses=dimension_statuses,
        dimension_applicability=dimension_applicability,
        critical_dimensions=critical_dimensions,
        agent_applicability=str(agent_usability.get("applicability", "unknown")),
    )
    maturity_score = model["score"]
    target_status = str(target.get("status", "unknown"))
    certified = (
        target_status == "ready"
        and audit_coverage.get("status") == "complete"
        and model["status"] == "certified"
        and dynamic_status in {"passed", "reused"}
    )
    return {
        "repo_id": repo_id,
        "display_name": Path(primary_path).name,
        "local_identity": {"primary_path": primary_path},
        "target_branch": str(target.get("branch")) if target.get("branch") else None,
        "target_branch_status": target_status,
        "target_head": target.get("head"),
        "target_state": _target_state_projection(target.get("target_state")),
        "audit_coverage": audit_coverage,
        "comparison_eligible": audit_coverage.get("comparison_eligible") is True,
        "maturity_score": maturity_score,
        "source_dimension_mean": source_mean,
        "maturity_status": "certified"
        if certified
        else "not_certified"
        if maturity_score is not None
        else "unknown",
        "repository_maturity": model,
        "dimension_scores": dict(sorted(scores.items())),
        "dimension_gaps": sorted(gaps, key=lambda item: item["dimension"])[:MAX_DIMENSION_GAPS],
        "quality_status": quality_status,
        "quality_outcome": quality_outcome,
        "finding_count": len(findings),
        "blocker_count": blockers,
        "dynamic_status": dynamic_status,
        "agent_usability": agent_usability,
        "behavior_assurance": _object(finding.get("behavior_assurance")),
        "cache_design": cache_design,
    }


def _quality_status(
    blockers: int, dynamic_status: str, statuses: list[str], agent_attention: bool
) -> str:
    if blockers or dynamic_status in {"failed", "timeout", "blocked"}:
        return "blocked"
    if dynamic_status in {"unavailable", "unknown"} or any(
        status in {"unknown", "stale"} for status in statuses
    ):
        return "unknown"
    if (
        dynamic_status in {"passed", "reused"}
        and not agent_attention
        and statuses
        and all(status in {"validated", "maintained", "not_applicable"} for status in statuses)
    ):
        return "healthy"
    return "attention"


def _gap(dimension: str, status: str, score: float | None, message: str) -> Mapping[str, Any]:
    return {
        "dimension": dimension,
        "status": status,
        "score": score,
        "message": (message or "Evidence is incomplete.")[:240],
    }


def _applicability(item: Mapping[str, Any], status: str) -> str:
    value = item.get("applicability")
    if isinstance(value, str) and value in {"applicable", "not_applicable", "unknown"}:
        return value
    if item.get("applicable") is False or status == "not_applicable":
        return "not_applicable"
    if item.get("applicable") is True:
        return "applicable"
    return "unknown"


def _target_state_projection(value: object) -> dict[str, Any]:
    state = value if isinstance(value, dict) else {}
    allowed = (
        "status",
        "reason",
        "local_head",
        "upstream",
        "upstream_head",
        "ahead",
        "behind",
        "safe_action",
    )
    return {key: state.get(key) for key in allowed if key in state}


def _required_string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise MaturityProjectionError(f"maturity feed field is missing: {key}")
    return item


def _object(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in value if isinstance(item, dict)]
