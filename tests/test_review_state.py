from pathlib import Path

from quality_runner.review_state import (
    accept_known_issue,
    edit_known_issue,
    finalize_cycle_state,
    known_issue_findings,
    load_known_issues,
    major_change_requires_reverification,
    remove_known_issue,
)


def test_known_issue_accept_edit_remove_and_repeat(tmp_path: Path) -> None:
    issue = accept_known_issue(tmp_path, fingerprint="fp", summary="Known", reason="accepted", owner="me")
    assert load_known_issues(tmp_path)[0]["id"] == issue["id"]
    edit_known_issue(tmp_path, issue["id"], summary="Updated")
    assert known_issue_findings(tmp_path, [{"fingerprint": "fp", "status": "open"}])[0]["classification"] == "known-accepted"
    remove_known_issue(tmp_path, issue["id"])
    assert load_known_issues(tmp_path) == []


def test_major_change_triggers_cover_declared_inputs() -> None:
    assert major_change_requires_reverification(baseline_changed=True)
    assert major_change_requires_reverification(default_branch_changed=True)
    assert major_change_requires_reverification(changed_files=["infra/deploy.yml"], configured_high_risk_paths=["infra"])
    assert major_change_requires_reverification(explicit=True)
    assert not major_change_requires_reverification(changed_files=["src/a.py"], configured_high_risk_paths=["infra"])


def test_cycle_finalization_classifies_resolved_and_accepted() -> None:
    state = finalize_cycle_state(cycle_id="c1", findings=[{"fingerprint": "open"}], prior_findings=[{"fingerprint": "gone"}, {"fingerprint": "open", "status": "accepted"}])
    statuses = {entry["fingerprint"]: entry["status"] for entry in state["entries"]}
    assert statuses == {"open": "accepted", "gone": "resolved"}
