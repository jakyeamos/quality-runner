from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypedDict


class LoopState(TypedDict):
    cycle_id: str
    iteration: int
    stop_condition: str
    selected_finding_ids: list[str]
    fixing_agent_status: str
    active_cycle: bool


def start_review_loop(*, cycle_id: str, stop_condition: str = "critical-high") -> LoopState:
    if stop_condition not in {"critical-high", "none"}:
        raise ValueError("stop condition must be critical-high or none")
    return {"cycle_id": cycle_id, "iteration": 1, "stop_condition": stop_condition, "selected_finding_ids": [], "fixing_agent_status": "not-started", "active_cycle": True}


def should_stop(findings: Sequence[Mapping[str, object]], stop_condition: str) -> bool:
    severities = {finding.get("severity") for finding in findings}
    if stop_condition == "critical-high":
        return not severities.intersection({"critical", "high"})
    if stop_condition == "none":
        return not findings
    raise ValueError("stop condition must be critical-high or none")


def select_handoff_findings(
    findings: Sequence[Mapping[str, object]], *, finding_ids: Sequence[str] = (), all_critical_high: bool = False
) -> list[dict[str, object]]:
    selected = set(finding_ids)
    return [dict(finding) for finding in findings if (finding.get("id") in selected) or (all_critical_high and finding.get("severity") in {"critical", "high"})]


def next_iteration(state: LoopState, *, selected_finding_ids: Sequence[str], fixing_agent_status: str = "complete") -> LoopState:
    if not state["active_cycle"]:
        raise ValueError("review loop is already finalized")
    return {**state, "iteration": state["iteration"] + 1, "selected_finding_ids": list(selected_finding_ids), "fixing_agent_status": fixing_agent_status}


def finalize_review_loop(state: LoopState, findings: Sequence[Mapping[str, object]]) -> dict[str, object]:
    return {"cycle_id": state["cycle_id"], "iteration": state["iteration"], "active": False, "stop_condition": state["stop_condition"], "stopped": should_stop(findings, state["stop_condition"]), "findings": [dict(finding) for finding in findings], "uncertainty": "fixing agent changed scope" if state["fixing_agent_status"] == "scope-changed" else None}
