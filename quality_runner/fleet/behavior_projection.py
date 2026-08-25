from __future__ import annotations

from typing import Any

from quality_runner.fleet.behavior_contract import (
    EDGE_CATEGORIES,
    LEGACY_CONTRACT_SCHEMA,
    MAX_SCENARIO_RECORDS,
    RESILIENCE_DIMENSIONS,
)


def empty_coverage() -> dict[str, Any]:
    return {
        "total": 0,
        "profiled": 0,
        "verified": 0,
        "stale": 0,
        "failed": 0,
        "blocked": 0,
        "unknown": 0,
        "profile_status": "missing",
        "resilience_profiled": 0,
        "resilience_profile_status": "missing",
        "per_tier": {},
        "per_edge_category": {},
        "per_resilience_dimension": {},
        "category_gaps": [],
        "resilience_gaps": [],
        "scenarios": [],
        "truncated": False,
    }


def coverage(
    requirements: list[dict[str, Any]],
    outcomes: dict[tuple[str, str], dict[str, Any]],
    contract_schema: str,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for requirement in requirements:
        outcome = outcomes.get(
            requirement_key(requirement),
            {"status": "unknown", "kind": "receipt_missing"},
        )
        status = _coverage_status(outcome)
        records.append(
            {
                "behavior_id": requirement["behavior_id"],
                "scenario_id": requirement["scenario_id"],
                "tier": requirement["tier"],
                "profiled": requirement["profiled"],
                "categories": requirement["categories"],
                "risk": requirement["risk"],
                "side_effects": requirement["side_effects"],
                "resilience_profiled": requirement["resilience_profiled"],
                "resilience_dimensions": requirement["resilience_dimensions"],
                "resilience_item_counts": requirement["resilience_item_counts"],
                "status": status,
                "verification_level": outcome.get("verification_level"),
                "receipt_id": outcome.get("receipt_id"),
                "freshness": (
                    "stale"
                    if status == "stale"
                    else "current"
                    if status == "verified"
                    else "unknown"
                ),
            }
        )
    total = len(records)
    profiled = sum(int(item["profiled"]) for item in records)
    resilience_profiled = sum(int(item["resilience_profiled"]) for item in records)
    profile_status = (
        "legacy"
        if contract_schema == LEGACY_CONTRACT_SCHEMA
        else "profiled"
        if total and profiled == total
        else "partially_profiled"
        if profiled
        else "unprofiled"
    )
    resilience_profile_status = (
        "legacy"
        if contract_schema == LEGACY_CONTRACT_SCHEMA
        else "profiled"
        if total and resilience_profiled == total
        else "partially_profiled"
        if resilience_profiled
        else "unprofiled"
    )
    result = {
        "total": total,
        "profiled": profiled,
        **{
            status: sum(int(item["status"] == status) for item in records)
            for status in ("verified", "stale", "failed", "blocked", "unknown")
        },
        "profile_status": profile_status,
        "resilience_profiled": resilience_profiled,
        "resilience_profile_status": resilience_profile_status,
        "per_tier": {
            str(tier): _summary([item for item in records if item["tier"] == tier])
            for tier in (0, 1, 2)
        },
        "per_edge_category": {
            category: _summary([item for item in records if category in item["categories"]])
            for category in sorted(EDGE_CATEGORIES)
            if any(category in item["categories"] for item in records)
        },
        "per_resilience_dimension": {
            dimension: {
                "scenario_count": sum(
                    int(dimension in item["resilience_dimensions"]) for item in records
                ),
                "item_count": sum(
                    int(item["resilience_item_counts"].get(dimension, 0)) for item in records
                ),
            }
            for dimension in RESILIENCE_DIMENSIONS
            if any(dimension in item["resilience_dimensions"] for item in records)
        },
        "category_gaps": [],
        "resilience_gaps": [],
        "scenarios": records[:MAX_SCENARIO_RECORDS],
        "truncated": len(records) > MAX_SCENARIO_RECORDS,
    }
    if profiled < total:
        result["category_gaps"].append(
            {"category": "unprofiled", "scenario_count": total - profiled}
        )
    if resilience_profiled < total:
        result["resilience_gaps"].append(
            {"dimension": "unprofiled", "scenario_count": total - resilience_profiled}
        )
    for dimension in RESILIENCE_DIMENSIONS:
        missing = sum(int(dimension not in item["resilience_dimensions"]) for item in records)
        if missing:
            result["resilience_gaps"].append(
                {"dimension": dimension, "scenario_count": missing}
            )
    for category, summary in result["per_edge_category"].items():
        if summary["verified"] < summary["total"]:
            result["category_gaps"].append(
                {
                    "category": category,
                    "scenario_count": summary["total"] - summary["verified"],
                }
            )
    return result


def requirement_key(requirement: dict[str, Any]) -> tuple[str, str]:
    return str(requirement["behavior_id"]), str(requirement["scenario_id"])


def _summary(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(records),
        "profiled": sum(int(item["profiled"]) for item in records),
        "resilience_profiled": sum(int(item["resilience_profiled"]) for item in records),
        **{
            status: sum(int(item["status"] == status) for item in records)
            for status in ("verified", "stale", "failed", "blocked", "unknown")
        },
    }


def _coverage_status(outcome: dict[str, Any]) -> str:
    if outcome.get("status") == "passed":
        return "verified"
    if outcome.get("kind") in {"receipt_stale", "verification_level_low"}:
        return "stale"
    if outcome.get("status") == "failed":
        return "failed"
    if outcome.get("status") == "blocked":
        return "blocked"
    return "unknown"
