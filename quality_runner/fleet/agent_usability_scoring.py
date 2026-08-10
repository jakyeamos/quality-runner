from __future__ import annotations

from typing import Any, cast

AGENT_USABILITY_DIMENSION_PREFIX = "agent_usability."
_GROWTH_SCORES = {"blocked": 0, "attention": 2, "healthy": 4}


def growth_health_score(status: object) -> int | None:
    return _GROWTH_SCORES.get(status) if isinstance(status, str) else None


def applicable_agent_usability_scores(assessment: object) -> list[dict[str, Any]]:
    if not isinstance(assessment, dict):
        return []
    payload = cast(dict[str, object], assessment)
    if (
        payload.get("applicability") == "not_applicable"
        or payload.get("status") == "not_applicable"
    ):
        return []
    scores: list[dict[str, Any]] = []
    lanes = payload.get("lanes")
    if isinstance(lanes, list):
        for raw_lane in cast(list[object], lanes):
            if not isinstance(raw_lane, dict):
                continue
            lane = cast(dict[str, object], raw_lane)
            if lane.get("applicable") is not True:
                continue
            identifier = lane.get("id")
            score = lane.get("score")
            if (
                isinstance(identifier, str)
                and identifier
                and isinstance(score, int | float)
                and 0 <= score <= 4
            ):
                scores.append(
                    {
                        "dimension": f"{AGENT_USABILITY_DIMENSION_PREFIX}{identifier}",
                        "score": float(score),
                        "status": str(lane.get("status", "unknown")),
                        "message": str(
                            lane.get("message", "Agent-usability evidence is incomplete.")
                        ),
                    }
                )
    growth = payload.get("growth_health")
    if isinstance(growth, dict):
        growth_payload = cast(dict[str, object], growth)
        score = growth_health_score(growth_payload.get("status"))
        if score is not None:
            scores.append(
                {
                    "dimension": f"{AGENT_USABILITY_DIMENSION_PREFIX}growth_health",
                    "score": float(score),
                    "status": str(growth_payload.get("status", "unknown")),
                    "message": str(
                        growth_payload.get("message", "Growth-health evidence is incomplete.")
                    ),
                }
            )
    return scores
