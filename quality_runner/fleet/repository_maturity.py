from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from quality_runner.fleet.maturity_model_contract import (
    PILLAR_DEFINITIONS,
    REPOSITORY_MATURITY_SCHEMA,
)

_CRITICAL_PILLARS = {
    "correctness_reliability",
    "security_privacy_supply_chain",
    "operability_release_safety",
}
_NON_FRESH_STATUSES = {"blocked", "stale", "unknown"}
_DIAGNOSTIC_PATTERNS = ("agent_usability.growth_health",)
_APPLICABILITY_VALUES = {"applicable", "not_applicable", "unknown"}


def build_repository_maturity(
    dimension_scores: Mapping[str, float | None],
    *,
    dimension_statuses: Mapping[str, str] | None = None,
    dimension_applicability: Mapping[str, str] | None = None,
    critical_dimensions: Sequence[str] = (),
    agent_applicability: str = "unknown",
) -> dict[str, Any]:
    """Build a capability-then-pillar projection without hiding unknowns."""
    statuses = {str(key): str(value) for key, value in (dimension_statuses or {}).items()}
    applicability = {
        str(key): _normalize_applicability(value)
        for key, value in (dimension_applicability or {}).items()
    }
    dimensions = {str(key): value for key, value in dimension_scores.items()}
    numeric_scores = {
        dimension: float(value)
        for dimension, value in dimensions.items()
        if isinstance(value, (int, float)) and 0 <= float(value) <= 4
    }
    assigned: set[str] = set()
    diagnostic_dimensions = sorted(
        dimension for dimension in dimensions if _matches_any(dimension, _DIAGNOSTIC_PATTERNS)
    )
    assigned.update(diagnostic_dimensions)
    pillars: list[dict[str, Any]] = []
    critical_reasons: list[str] = []
    unknown_capability_applicability: list[str] = []

    for definition in PILLAR_DEFINITIONS:
        capabilities: list[dict[str, Any]] = []
        for capability_id, capability_definition in definition["capabilities"].items():
            patterns = capability_definition["patterns"]
            producer_dimensions = sorted(
                dimension for dimension in dimensions if _matches_any(dimension, patterns)
            )
            assigned.update(producer_dimensions)
            capability_applicability = _capability_applicability(
                str(capability_definition["applicability"]),
                producer_dimensions,
                applicability,
                agent_applicability,
            )
            if capability_applicability == "unknown":
                unknown_capability_applicability.append(f"{definition['id']}:{capability_id}")
            capability_scores = {
                dimension: numeric_scores[dimension]
                for dimension in producer_dimensions
                if dimension in numeric_scores
                and applicability.get(dimension, "applicable") == "applicable"
            }
            score = (
                _mean(capability_scores.values())
                if capability_applicability == "applicable"
                else None
            )
            capability_statuses = [
                statuses.get(dimension, "unknown") for dimension in capability_scores
            ]
            capabilities.append(
                {
                    "id": capability_id,
                    "applicability": capability_applicability,
                    "status": _capability_status(
                        capability_applicability, score, capability_statuses
                    ),
                    "score": score,
                    "dimension_scores": dict(sorted(capability_scores.items())),
                    "producer_dimensions": producer_dimensions,
                }
            )

        pillar_applicability = _pillar_applicability(
            str(definition["applicability"]), capabilities, agent_applicability
        )
        applicable_capabilities = [
            capability for capability in capabilities if capability["applicability"] == "applicable"
        ]
        scored_capabilities = [
            capability for capability in applicable_capabilities if capability["score"] is not None
        ]
        score = (
            _mean(capability["score"] for capability in scored_capabilities)
            if pillar_applicability == "applicable"
            else None
        )
        pillar_dimensions = {
            dimension: numeric_scores[dimension]
            for capability in capabilities
            for dimension in capability["dimension_scores"]
        }
        blocking_dimensions = sorted(
            dimension
            for dimension in critical_dimensions
            if any(dimension in capability["producer_dimensions"] for capability in capabilities)
            and definition["id"] in _CRITICAL_PILLARS
        )
        critical_reasons.extend(
            f"{definition['id']}:{dimension}" for dimension in blocking_dimensions
        )
        missing_capabilities = sorted(
            str(capability["id"])
            for capability in applicable_capabilities
            if capability["score"] is None
        )
        capability_coverage = (
            len(scored_capabilities) / len(applicable_capabilities)
            if applicable_capabilities
            else 0.0
        )
        fresh_capability_count = sum(
            capability["score"] is not None and capability["status"] not in _NON_FRESH_STATUSES
            for capability in applicable_capabilities
        )
        fresh_capability_coverage = (
            fresh_capability_count / len(applicable_capabilities)
            if applicable_capabilities
            else 0.0
        )
        pillars.append(
            {
                "id": definition["id"],
                "label": definition["label"],
                "weight": definition["weight"],
                "applicability": pillar_applicability,
                "status": _pillar_status(
                    pillar_applicability,
                    score,
                    capabilities,
                    bool(blocking_dimensions),
                ),
                "score": score,
                "capabilities": capabilities,
                "capability_coverage": round(capability_coverage, 3),
                "fresh_capability_coverage": round(fresh_capability_coverage, 3),
                "dimension_scores": dict(sorted(pillar_dimensions.items())),
                "missing_capabilities": missing_capabilities,
                "critical_dimensions": blocking_dimensions,
            }
        )

    applicable_pillars = [pillar for pillar in pillars if pillar["applicability"] == "applicable"]
    assessed_pillars = [pillar for pillar in applicable_pillars if pillar["score"] is not None]
    applicable_weight = sum(float(pillar["weight"]) for pillar in applicable_pillars)
    scored_weight = sum(float(pillar["weight"]) for pillar in assessed_pillars)
    evidenced_weight = sum(
        float(pillar["weight"]) * float(pillar["capability_coverage"])
        for pillar in applicable_pillars
    )
    fresh_weight = sum(
        float(pillar["weight"]) * float(pillar["fresh_capability_coverage"])
        for pillar in applicable_pillars
    )
    weighted_total = sum(
        float(pillar["score"]) * float(pillar["weight"]) for pillar in assessed_pillars
    )
    uncapped_score = round(weighted_total / scored_weight, 3) if scored_weight else None
    cap = 2.0 if critical_reasons else None
    score = min(uncapped_score, cap) if uncapped_score is not None and cap else uncapped_score
    unknown_pillar_applicability = [
        str(pillar["id"]) for pillar in pillars if pillar["applicability"] == "unknown"
    ]
    evidence_coverage = round(evidenced_weight / applicable_weight, 3) if applicable_weight else 0.0
    fresh_evidence_coverage = (
        round(fresh_weight / applicable_weight, 3) if applicable_weight else 0.0
    )
    certified = bool(
        score == 4
        and evidence_coverage == 1
        and not critical_reasons
        and not unknown_pillar_applicability
        and not unknown_capability_applicability
        and all(pillar["status"] == "maintained" for pillar in applicable_pillars)
    )
    if score is None:
        status = "unknown"
    elif critical_reasons:
        status = "blocked"
    elif certified:
        status = "certified"
    elif evidence_coverage < 1 or unknown_pillar_applicability or unknown_capability_applicability:
        status = "provisional"
    else:
        status = "measured"

    return {
        "schema": REPOSITORY_MATURITY_SCHEMA,
        "score": score,
        "uncapped_score": uncapped_score,
        "status": status,
        "pillars": pillars,
        "evidence": {
            "applicable_pillar_count": len(applicable_pillars),
            "assessed_pillar_count": len(assessed_pillars),
            "applicable_weight": round(applicable_weight, 3),
            "assessed_weight": round(evidenced_weight, 3),
            "evidence_coverage": evidence_coverage,
            "fresh_evidence_coverage": fresh_evidence_coverage,
            "unknown_applicability": unknown_pillar_applicability,
            "unknown_capability_applicability": sorted(unknown_capability_applicability),
            "unmapped_dimensions": sorted(set(dimensions) - assigned),
            "diagnostic_dimensions": diagnostic_dimensions,
        },
        "critical_cap": {
            "applied": cap is not None,
            "maximum_score": cap,
            "reasons": sorted(critical_reasons),
        },
    }


def pillar_means(models: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    values: dict[str, list[float]] = {str(item["id"]): [] for item in PILLAR_DEFINITIONS}
    for model in models:
        for pillar in model.get("pillars", []):
            if not isinstance(pillar, dict):
                continue
            pillar_id = str(pillar.get("id", ""))
            score = pillar.get("score")
            if pillar_id in values and isinstance(score, (int, float)):
                values[pillar_id].append(float(score))
    return {
        pillar_id: round(sum(scores) / len(scores), 3) if scores else None
        for pillar_id, scores in values.items()
    }


def capability_producers(dimensions: Sequence[str]) -> dict[str, list[str]]:
    """Return canonical producer coverage for reverse-contract tests and docs."""
    return {
        f"{pillar['id']}:{capability_id}": sorted(
            dimension for dimension in dimensions if _matches_any(dimension, capability["patterns"])
        )
        for pillar in PILLAR_DEFINITIONS
        for capability_id, capability in pillar["capabilities"].items()
    }


def _capability_applicability(
    policy: str,
    producer_dimensions: Sequence[str],
    applicability: Mapping[str, str],
    agent_applicability: str,
) -> str:
    if policy == "required":
        return "applicable"
    if policy == "agent_conditional" and agent_applicability == "not_applicable":
        return "not_applicable"
    states = [applicability.get(dimension, "applicable") for dimension in producer_dimensions]
    if any(state == "applicable" for state in states):
        return "applicable"
    if states and all(state == "not_applicable" for state in states):
        return "not_applicable"
    if policy == "agent_conditional" and agent_applicability == "applicable":
        return "applicable"
    return "unknown"


def _pillar_applicability(
    policy: str, capabilities: Sequence[Mapping[str, Any]], agent_applicability: str
) -> str:
    if policy == "required":
        return "applicable"
    if policy == "agent_conditional" and agent_applicability == "not_applicable":
        return "not_applicable"
    states = [str(capability["applicability"]) for capability in capabilities]
    if any(state == "applicable" for state in states):
        return "applicable"
    if states and all(state == "not_applicable" for state in states):
        return "not_applicable"
    return "unknown"


def _capability_status(applicability: str, score: float | None, statuses: Sequence[str]) -> str:
    if applicability == "not_applicable":
        return "not_applicable"
    if applicability == "unknown" or score is None:
        return "unknown"
    if any(status in _NON_FRESH_STATUSES for status in statuses):
        return next(status for status in ("blocked", "stale", "unknown") if status in statuses)
    return "maintained" if score == 4 else "attention"


def _pillar_status(
    applicability: str,
    score: float | None,
    capabilities: Sequence[Mapping[str, Any]],
    critical: bool,
) -> str:
    if applicability == "not_applicable":
        return "not_applicable"
    if applicability == "unknown" or score is None:
        return "unknown"
    if critical:
        return "blocked"
    applicable = [
        capability for capability in capabilities if capability["applicability"] == "applicable"
    ]
    statuses = [str(capability["status"]) for capability in applicable]
    if any(status in _NON_FRESH_STATUSES for status in statuses):
        return next(status for status in ("blocked", "stale", "unknown") if status in statuses)
    return (
        "maintained"
        if applicable and all(capability["score"] == 4 for capability in applicable)
        else "attention"
    )


def _normalize_applicability(value: object) -> str:
    return value if isinstance(value, str) and value in _APPLICABILITY_VALUES else "unknown"


def _matches_any(dimension: str, patterns: Sequence[str]) -> bool:
    return any(dimension == pattern or dimension.startswith(pattern) for pattern in patterns)


def _mean(values: Any) -> float | None:
    items = [float(value) for value in values if isinstance(value, (int, float))]
    return round(sum(items) / len(items), 3) if items else None
