from __future__ import annotations

from pathlib import Path

import pytest

from quality_runner.application import journey_outcomes
from quality_runner.compatibility import journey_outcomes as legacy_journey_outcomes
from quality_runner.compatibility import review_mcp


def test_legacy_journey_outcomes_are_application_facades() -> None:
    assert legacy_journey_outcomes.audit_journey_outcome is journey_outcomes.audit_journey_outcome
    assert legacy_journey_outcomes.review_journey_outcome is journey_outcomes.review_journey_outcome
    assert legacy_journey_outcomes.review_mcp_input_schema is review_mcp.review_mcp_input_schema
    assert (
        legacy_journey_outcomes.review_mcp_journey_outcome is review_mcp.review_mcp_journey_outcome
    )
    assert legacy_journey_outcomes.runs_journey_outcome is journey_outcomes.runs_journey_outcome
    assert legacy_journey_outcomes.verify_journey_outcome is journey_outcomes.verify_journey_outcome


@pytest.mark.parametrize(
    ("branches", "expected_switch"),
    [(("main", "main"), False), (("main", "feature"), True)],
)
def test_audit_uses_observed_branch_transition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    branches: tuple[str, str],
    expected_switch: bool,
) -> None:
    observed_branches = iter(branches)
    monkeypatch.setattr(
        journey_outcomes,
        "checked_out_branch",
        lambda _repo_root: next(observed_branches),
    )
    monkeypatch.setattr(
        journey_outcomes,
        "run_payload",
        lambda **_kwargs: {
            "schema": "quality-runner-run-result-v0.1",
            "status": "planned",
            "run_id": "branch-audit",
            "artifact_paths": {},
        },
    )

    outcome = journey_outcomes.audit_journey_outcome(
        repo_root=tmp_path,
        run_id="branch-audit",
        profile=None,
        ci_status_json=None,
        include_ignored_paths=[],
        checkout_most_advanced_branch=True,
        skill_review_report=None,
        intent=None,
        inspect_only=False,
    )

    assert outcome["writes"]["source_worktree"] == (
        "branch-switched" if expected_switch else "unchanged"
    )
    assert outcome["safety"]["source_worktree_mutated"] is expected_switch


def test_verify_uses_observed_branch_transition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed_branches = iter(("main", "feature"))
    monkeypatch.setattr(
        journey_outcomes,
        "checked_out_branch",
        lambda _repo_root: next(observed_branches),
    )
    monkeypatch.setattr(
        journey_outcomes,
        "verify_gates_payload",
        lambda **_kwargs: {
            "schema": "quality-runner-verify-gates-result-v0.1",
            "status": "blocked",
            "run_id": "branch-verify",
            "artifact_paths": {},
        },
    )
    monkeypatch.setattr(
        journey_outcomes,
        "_gate_verification",
        lambda _repo_root, _payload: {
            "execute_discovered_gates": False,
            "verification_context": {"execution_authorized": False},
            "gates": [],
        },
    )

    outcome = journey_outcomes.verify_journey_outcome(
        repo_root=tmp_path,
        run_id="branch-verify",
        profile=None,
        ci_status_json=None,
        timeout_seconds=120,
        checkout_most_advanced_branch=True,
        execute_discovered_gates=False,
        read_only_gates=False,
        allow_mutating_gates=False,
        worktree_mode="in-place",
        allow_dirty_worktree_verify=False,
        skill_review_report=None,
        intent=None,
    )

    assert outcome["writes"]["source_worktree"] == "branch-switched"
    assert outcome["safety"]["source_worktree_mutated"] is True
