from __future__ import annotations

from typing import Any

from quality_runner.fleet.behavior_contract import (
    AUTOMATION_MODES,
    CONTRACT_SCHEMA,
    CONTRACT_SCHEMAS,
    EDGE_CATEGORIES,
    EDGE_RISKS,
    EDGE_SIDE_EFFECTS,
    LEGACY_CONTRACT_SCHEMA,
    VERIFICATION_LEVELS,
)
from quality_runner.fleet.behavior_support import (
    object_value,
    object_values,
    string_value,
    string_values,
)


def contract_errors(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    schema = contract.get("schema")
    if schema not in CONTRACT_SCHEMAS:
        errors.append(f"schema must be {CONTRACT_SCHEMA} or compatible {LEGACY_CONTRACT_SCHEMA}")
    applicability = contract.get("applicability", "applicable")
    if applicability not in {"applicable", "not_applicable"}:
        errors.append("applicability must be applicable or not_applicable")
    if applicability == "not_applicable":
        if not string_value(contract.get("reason")):
            errors.append("not_applicable requires a non-empty reason")
        if object_values(contract.get("behaviors")):
            errors.append("not_applicable cannot declare behaviors")
        return errors
    if not string_values(contract.get("approved_producers", ["quality-runner"])):
        errors.append("approved_producers must contain at least one producer id")
    behaviors = object_values(contract.get("behaviors"))
    if not behaviors:
        errors.append("applicable contracts require at least one behavior")
    behavior_ids: set[str] = set()
    for index, behavior in enumerate(behaviors):
        label = f"behaviors[{index}]"
        behavior_id = string_value(behavior.get("id"))
        if not behavior_id:
            errors.append(f"{label}.id must be non-empty")
        elif behavior_id in behavior_ids:
            errors.append(f"duplicate behavior id: {behavior_id}")
        else:
            behavior_ids.add(behavior_id)
        if not string_value(behavior.get("title")):
            errors.append(f"{label}.title must be non-empty")
        if behavior.get("tier") not in {0, 1, 2}:
            errors.append(f"{label}.tier must be 0, 1, or 2")
        if behavior.get("automation") not in AUTOMATION_MODES:
            errors.append(f"{label}.automation must be permanent, on_demand, or manual")
        if not string_values(behavior.get("change_triggers")):
            errors.append(f"{label}.change_triggers must contain at least one path pattern")
        if schema == CONTRACT_SCHEMA and not string_values(behavior.get("invariants")):
            errors.append(f"{label}.invariants must contain at least one invariant in v2")
        scenarios = object_values(behavior.get("scenarios"))
        if not scenarios:
            errors.append(f"{label}.scenarios must contain at least one scenario")
        scenario_ids: set[str] = set()
        for scenario_index, scenario in enumerate(scenarios):
            scenario_label = f"{label}.scenarios[{scenario_index}]"
            scenario_id = string_value(scenario.get("id"))
            if not scenario_id:
                errors.append(f"{scenario_label}.id must be non-empty")
            elif scenario_id in scenario_ids:
                errors.append(f"duplicate scenario id in {behavior_id}: {scenario_id}")
            else:
                scenario_ids.add(scenario_id)
            if not string_value(scenario.get("title")) or not string_value(scenario.get("oracle")):
                errors.append(f"{scenario_label}.title and oracle must be non-empty")
            if scenario.get("verification_level") not in VERIFICATION_LEVELS:
                errors.append(f"{scenario_label}.verification_level is unsupported")
            profile = scenario.get("edge_profile")
            if profile is not None:
                if not isinstance(profile, dict):
                    errors.append(f"{scenario_label}.edge_profile must be an object")
                    continue
                categories = string_values(profile.get("categories"))
                if not categories or any(item not in EDGE_CATEGORIES for item in categories):
                    errors.append(
                        f"{scenario_label}.edge_profile.categories must contain canonical categories"
                    )
                if profile.get("risk") not in EDGE_RISKS:
                    errors.append(f"{scenario_label}.edge_profile.risk must be routine or hostile")
                if profile.get("side_effects") not in EDGE_SIDE_EFFECTS:
                    errors.append(
                        f"{scenario_label}.edge_profile.side_effects must be none, reversible, or destructive"
                    )
    return errors


def requirements(contract: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    is_v2 = contract.get("schema") == CONTRACT_SCHEMA
    for behavior in object_values(contract.get("behaviors")):
        invariants = string_values(behavior.get("invariants")) if is_v2 else []
        for scenario in object_values(behavior.get("scenarios")):
            profile = object_value(scenario.get("edge_profile")) if is_v2 else {}
            result.append(
                {
                    "behavior_id": behavior["id"],
                    "scenario_id": scenario["id"],
                    "minimum_verification_level": scenario["verification_level"],
                    "change_triggers": behavior["change_triggers"],
                    "tier": behavior["tier"],
                    "required": scenario.get("required", True) is not False,
                    "invariants": invariants,
                    "profiled": bool(profile),
                    "categories": string_values(profile.get("categories")),
                    "risk": profile.get("risk"),
                    "side_effects": profile.get("side_effects"),
                }
            )
    return result
