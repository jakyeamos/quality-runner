from quality_runner.review_loop import (
    finalize_review_loop,
    next_iteration,
    select_handoff_findings,
    should_stop,
    start_review_loop,
)


def test_stop_conditions_preserve_medium_findings() -> None:
    findings = [{"id": "h", "severity": "high"}, {"id": "m", "severity": "medium"}]
    assert not should_stop(findings, "critical-high")
    assert should_stop([{"id": "m", "severity": "medium"}], "critical-high")
    assert not should_stop(findings, "none")
    assert should_stop([], "none")


def test_loop_handoff_and_fresh_iteration_state() -> None:
    state = start_review_loop(cycle_id="c1")
    selected = select_handoff_findings(
        [{"id": "h", "severity": "high"}, {"id": "m", "severity": "medium"}], all_critical_high=True
    )
    next_state = next_iteration(state, selected_finding_ids=["h"])
    assert [item["id"] for item in selected] == ["h"]
    assert next_state["iteration"] == 2
    assert next_state["active_cycle"]
    final = finalize_review_loop(next_state, [{"id": "m", "severity": "medium"}])
    assert final["stopped"]
    assert final["findings"][0]["id"] == "m"
