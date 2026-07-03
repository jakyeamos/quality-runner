from __future__ import annotations

from typing import Any


def handoff_status(
    *,
    remediation_plan: dict[str, Any],
    capability_map: dict[str, Any] | None,
    missing_repo_owned_gates: list[dict[str, str]],
) -> str:
    slices = _slices(remediation_plan)
    execution_results = _capability_execution_results(capability_map)
    if execution_results and all(result == "passed" for result in execution_results) and not slices:
        return "gates-clean"
    if any(result in {"passed", "failed"} for result in execution_results):
        return "gates-executed"
    if _available_capabilities(capability_map) and not missing_repo_owned_gates:
        return "gates-discovered"
    return "clean" if not slices else "planned"


def _available_capabilities(capability_map: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(capability_map, dict):
        return []
    available = capability_map.get("available")
    if not isinstance(available, list):
        return []
    return [capability for capability in available if isinstance(capability, dict)]


def _capability_execution_results(capability_map: dict[str, Any] | None) -> list[str]:
    results: list[str] = []
    for capability in _available_capabilities(capability_map):
        state = capability.get("verification_state")
        if not isinstance(state, dict):
            continue
        execution = state.get("execution")
        result = state.get("result")
        if execution in {"ci-executed", "local-executed"} and isinstance(result, str):
            results.append(result)
    return results


def _slices(plan: dict[str, Any]) -> list[dict[str, str]]:
    slices = plan.get("slices")
    if not isinstance(slices, list):
        return []
    return [
        {"id": slice_item["id"]}
        for slice_item in slices
        if isinstance(slice_item, dict)
        and isinstance(slice_item.get("id"), str)
        and slice_item["id"]
    ]
