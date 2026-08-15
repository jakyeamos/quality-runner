from __future__ import annotations

import json
from pathlib import Path

from quality_runner.fleet.contracts import DIMENSION_LABELS
from quality_runner.fleet.repository_maturity import (
    build_repository_maturity,
    capability_producers,
)

AGENT_SCORING_DIMENSIONS = (
    "agent_usability.behavior_evidence",
    "agent_usability.documentation_contract",
    "agent_usability.freshness_portability",
    "agent_usability.tool_skill_coverage",
)
ROOT = Path(__file__).resolve().parents[1]


def test_every_canonical_dimension_maps_to_exactly_one_pillar() -> None:
    dimensions = (*DIMENSION_LABELS, *AGENT_SCORING_DIMENSIONS)
    model = build_repository_maturity(
        {dimension: 4 for dimension in dimensions},
        agent_applicability="applicable",
    )

    assignments = {
        dimension: [
            pillar["id"] for pillar in model["pillars"] if dimension in pillar["dimension_scores"]
        ]
        for dimension in dimensions
    }

    assert model["evidence"]["unmapped_dimensions"] == []
    assert all(len(pillars) == 1 for pillars in assignments.values()), assignments


def test_every_capability_has_a_canonical_producer() -> None:
    producers = capability_producers((*DIMENSION_LABELS, *AGENT_SCORING_DIMENSIONS))

    assert producers
    assert all(dimensions for dimensions in producers.values()), producers


def test_public_schema_requires_capability_and_applicability_evidence() -> None:
    schema = json.loads(
        (ROOT / "quality_runner/schemas/maturity-feed.schema.json").read_text(encoding="utf-8")
    )
    repository_model = schema["properties"]["repositories"]["items"]["properties"][
        "repository_maturity"
    ]
    pillar = repository_model["properties"]["pillars"]["items"]
    evidence = repository_model["properties"]["evidence"]

    assert {
        "capabilities",
        "capability_coverage",
        "fresh_capability_coverage",
    } <= set(pillar["required"])
    assert {
        "unknown_capability_applicability",
        "diagnostic_dimensions",
    } <= set(evidence["required"])


def test_pillars_prevent_dimension_volume_from_domination() -> None:
    baseline = build_repository_maturity(
        {
            "quality_commands": 4,
            "security_constraints": 2,
            "architecture_boundaries": 4,
            "failure_modes": 4,
        },
        dimension_statuses={
            "quality_commands": "maintained",
            "security_constraints": "attention",
            "architecture_boundaries": "maintained",
            "failure_modes": "maintained",
        },
    )
    expanded = build_repository_maturity(
        {
            "quality_commands": 4,
            "behavior_assurance": 4,
            "dynamic_verification": 4,
            "security_constraints": 2,
            "architecture_boundaries": 4,
            "failure_modes": 4,
        },
        dimension_statuses={
            "quality_commands": "maintained",
            "behavior_assurance": "maintained",
            "dynamic_verification": "maintained",
            "security_constraints": "attention",
            "architecture_boundaries": "maintained",
            "failure_modes": "maintained",
        },
    )

    assert baseline["score"] == expanded["score"]


def test_critical_security_blocker_caps_overall_score() -> None:
    model = build_repository_maturity(
        {
            "quality_commands": 4,
            "security_constraints": 4,
            "architecture_boundaries": 4,
            "failure_modes": 4,
        },
        dimension_statuses={
            "quality_commands": "maintained",
            "security_constraints": "blocked",
            "architecture_boundaries": "maintained",
            "failure_modes": "maintained",
        },
        critical_dimensions=["security_constraints"],
    )

    assert model["uncapped_score"] == 4
    assert model["score"] == 2
    assert model["status"] == "blocked"
    assert model["critical_cap"] == {
        "applied": True,
        "maximum_score": 2.0,
        "reasons": ["security_privacy_supply_chain:security_constraints"],
    }


def test_unknown_conditionals_are_not_zero_or_not_applicable() -> None:
    model = build_repository_maturity(
        {
            "quality_commands": 3,
            "security_constraints": 3,
            "architecture_boundaries": 3,
            "failure_modes": 3,
        },
        dimension_statuses={
            key: "attention"
            for key in (
                "quality_commands",
                "security_constraints",
                "architecture_boundaries",
                "failure_modes",
            )
        },
    )

    assert model["score"] == 3
    assert model["status"] == "provisional"
    assert model["evidence"]["unknown_applicability"] == [
        "user_facing_quality",
        "human_agent_usability",
    ]


def test_agent_not_applicable_stays_out_of_denominator() -> None:
    model = build_repository_maturity(
        {
            "quality_commands": 4,
            "security_constraints": 4,
            "architecture_boundaries": 4,
            "failure_modes": 4,
        },
        dimension_statuses={
            key: "maintained"
            for key in (
                "quality_commands",
                "security_constraints",
                "architecture_boundaries",
                "failure_modes",
            )
        },
        agent_applicability="not_applicable",
    )

    agent = next(pillar for pillar in model["pillars"] if pillar["id"] == "human_agent_usability")
    assert agent["applicability"] == "not_applicable"
    assert agent["score"] is None


def test_one_detector_does_not_claim_complete_pillar_evidence() -> None:
    model = build_repository_maturity(
        {
            "quality_commands": 4,
            "security_constraints": 4,
            "architecture_boundaries": 4,
            "failure_modes": 4,
        },
        dimension_statuses={
            key: "maintained"
            for key in (
                "quality_commands",
                "security_constraints",
                "architecture_boundaries",
                "failure_modes",
            )
        },
        agent_applicability="not_applicable",
    )

    assert model["score"] == 4
    assert model["status"] == "provisional"
    assert model["evidence"]["assessed_pillar_count"] == 4
    assert model["evidence"]["assessed_weight"] == 0.487
    assert model["evidence"]["evidence_coverage"] == 0.608
    by_id = {pillar["id"]: pillar for pillar in model["pillars"]}
    assert by_id["correctness_reliability"]["missing_capabilities"]
    assert by_id["maintainability_evolvability"]["missing_capabilities"]
    assert any(
        value.startswith(("security_privacy_supply_chain:", "operability_release_safety:"))
        for value in model["evidence"]["unknown_capability_applicability"]
    )


def test_capability_means_prevent_overlapping_dimensions_from_dominating() -> None:
    model = build_repository_maturity(
        {
            "implementation_examples": 0,
            "agent_usability.documentation_contract": 4,
            "skill_contract_quality": 4,
            "agent_usability.tool_skill_coverage": 4,
            "agent_usability.behavior_evidence": 4,
            "context_routing": 4,
            "agent_usability.freshness_portability": 4,
        },
        agent_applicability="applicable",
    )

    pillar = next(item for item in model["pillars"] if item["id"] == "human_agent_usability")
    assert pillar["score"] == 3.5


def test_explicit_not_applicable_capability_stays_out_of_denominator() -> None:
    model = build_repository_maturity(
        {
            "accessibility": None,
            "performance": 4,
            "critical_user_journeys": 4,
            "web_readiness": 4,
        },
        dimension_applicability={
            "accessibility": "not_applicable",
            "performance": "applicable",
            "critical_user_journeys": "applicable",
            "web_readiness": "applicable",
        },
    )

    pillar = next(item for item in model["pillars"] if item["id"] == "user_facing_quality")
    accessibility = next(
        item for item in pillar["capabilities"] if item["id"] == "accessible_experience"
    )
    assert accessibility["applicability"] == "not_applicable"
    assert pillar["score"] == 4
