from __future__ import annotations

from pathlib import Path

from quality_runner.application.outcome_projection import (
    project_audit_outcome,
    project_review_outcome,
    project_runs_outcome,
    project_verify_outcome,
)
from quality_runner.cli_outcome import render_outcome


def test_audit_outcome_leads_with_findings_and_handoff() -> None:
    outcome = project_audit_outcome(
        _payload(
            schema="quality-runner-run-result-v0.1",
            status="planned",
            run_id="audit-001",
            artifact_paths={
                "agent_handoff_md": "/repo/.quality-runner/runs/audit-001/agent-handoff.md"
            },
        ),
        repo_root=Path("/repo"),
        inspect_only=False,
        branch_switched=False,
    )

    assert outcome["state"] == "action-required"
    assert outcome["assessment"] == "findings"
    assert outcome["confidence"]["level"] == "observed"
    assert outcome["writes"]["state"] == "artifacts-written"
    assert outcome["safety"]["mode"] == "scan-only"
    assert outcome["next_action"]["kind"] == "read-handoff"


def test_audit_branch_switch_is_reported_only_when_observed() -> None:
    outcome = project_audit_outcome(
        _payload(
            schema="quality-runner-run-result-v0.1",
            status="planned",
            run_id="audit-branch",
            artifact_paths={},
        ),
        repo_root=Path("/repo"),
        inspect_only=False,
        branch_switched=True,
    )

    assert outcome["writes"]["source_worktree"] == "branch-switched"
    assert outcome["safety"]["source_worktree_mutated"] is True


def test_outcome_commands_quote_repo_paths_and_run_ids() -> None:
    outcome = project_audit_outcome(
        _payload(
            schema="quality-runner-run-result-v0.1",
            status="planned",
            run_id="audit;run",
            artifact_paths={},
        ),
        repo_root=Path("/repo with space;$(boom)"),
        inspect_only=False,
        branch_switched=False,
    )

    assert outcome["next_action"]["command"] == (
        "quality-runner export-handoff '/repo with space;$(boom)' --run-id 'audit;run'"
    )


def test_review_packet_ready_is_never_projected_as_clean() -> None:
    outcome = project_review_outcome(
        _payload(
            schema="quality-runner-review-result-v0.1",
            status="review-not-run",
            run_id="review-001",
            next_action="Provide an independent review response.",
        ),
        repo_root=Path("/repo"),
    )

    assert outcome["state"] == "awaiting-evidence"
    assert outcome["assessment"] == "packet-ready"
    assert outcome["confidence"]["level"] == "none"
    assert outcome["next_action"]["kind"] == "provide-review-output"


def test_verify_consent_blocked_outcome_preserves_explicit_authorization() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="blocked",
            run_id="verify-001",
        ),
        repo_root=Path("/repo"),
        verification=_payload(
            schema="quality-runner-gate-verification-v0.2",
            status="blocked",
            timeout_seconds=120,
            execute_discovered_gates=False,
            verification_context={"execution_authorized": False, "worktree_mode": "in-place"},
            gates=[
                {
                    "id": "tests",
                    "status": "skipped",
                    "skip_type": "execution-consent-required",
                    "reason": "Discovered command was recorded as evidence only.",
                }
            ],
        ),
    )

    assert outcome["state"] == "blocked"
    assert outcome["assessment"] == "evidence-incomplete"
    assert outcome["safety"]["mode"] == "evidence-only"
    assert outcome["next_action"]["kind"] == "authorize-verification"
    assert outcome["next_action"]["requires_authorization"] is True
    assert "--worktree-mode disposable" in outcome["next_action"]["command"]


def test_verify_disposable_success_is_confirmed() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="passed",
            run_id="verify-002",
        ),
        repo_root=Path("/repo"),
        verification=_payload(
            schema="quality-runner-gate-verification-v0.1",
            status="passed",
            timeout_seconds=120,
            execute_discovered_gates=True,
            verification_context={
                "execution_authorized": True,
                "worktree_mode": "disposable",
                "mutations_isolated": True,
            },
            gates=[{"id": "tests", "status": "passed"}],
        ),
    )

    assert outcome["state"] == "complete"
    assert outcome["assessment"] == "gates-passed"
    assert outcome["confidence"]["level"] == "confirmed"
    assert outcome["safety"]["mode"] == "disposable-execution"
    assert outcome["safety"]["commands_executed"] is True


def test_verify_selected_gate_success_remains_scoped_and_limited() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="passed",
            run_id="verify-selected",
        ),
        repo_root=Path("/repo"),
        verification=_payload(
            schema="quality-runner-gate-verification-v0.2",
            status="passed",
            timeout_seconds=120,
            execute_discovered_gates=True,
            only_gate_ids=["tests"],
            verification_context={
                "execution_authorized": True,
                "worktree_mode": "disposable",
                "mutations_isolated": True,
            },
            gates=[{"id": "tests", "status": "passed"}],
        ),
    )

    assert outcome["state"] == "awaiting-evidence"
    assert outcome["assessment"] == "evidence-incomplete"
    assert outcome["confidence"]["level"] == "limited"
    assert outcome["confidence"]["limitations"] == [
        "Verification was scoped to selected gate(s): tests; other discovered gates were not run."
    ]


def test_verify_execution_without_disposable_proof_stays_limited() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="passed",
            run_id="verify-legacy",
        ),
        repo_root=Path("/repo"),
        verification=_payload(
            schema="quality-runner-gate-verification-v0.1",
            status="passed",
            timeout_seconds=120,
            execute_discovered_gates=True,
            verification_context={
                "execution_authorized": True,
                "worktree_mode": "in-place",
                "mutations_isolated": False,
            },
            gates=[{"id": "tests", "status": "passed"}],
        ),
    )

    assert outcome["confidence"]["level"] == "limited"
    assert outcome["safety"]["mode"] == "evidence-only"
    assert outcome["safety"]["commands_executed"] is True
    assert outcome["safety"]["requires_explicit_authorization"] is False


def test_verify_missing_artifact_never_claims_a_passed_result() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="passed",
            run_id="verify-missing",
        ),
        repo_root=Path("/repo"),
        verification=None,
    )

    assert outcome["state"] == "awaiting-evidence"
    assert outcome["assessment"] == "evidence-incomplete"
    assert outcome["next_action"]["kind"] == "inspect-run"


def test_verify_incomplete_artifact_never_claims_a_passed_result() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="passed",
            run_id="verify-incomplete",
        ),
        repo_root=Path("/repo"),
        verification={},
    )

    assert outcome["state"] == "awaiting-evidence"
    assert outcome["assessment"] == "evidence-incomplete"
    assert outcome["next_action"]["kind"] == "inspect-run"


def test_verify_schema_incomplete_artifact_never_claims_a_passed_result() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="passed",
            run_id="verify-schema-incomplete",
        ),
        repo_root=Path("/repo"),
        verification=_payload(
            schema="quality-runner-gate-verification-v0.1",
            status="passed",
            gates=[],
        ),
    )

    assert outcome["state"] == "awaiting-evidence"
    assert outcome["assessment"] == "evidence-incomplete"


def test_verify_inconsistent_artifact_never_claims_a_passed_result() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="passed",
            run_id="verify-inconsistent",
        ),
        repo_root=Path("/repo"),
        verification=_payload(
            schema="quality-runner-gate-verification-v0.1",
            status="blocked",
            timeout_seconds=120,
            gates=[],
        ),
    )

    assert outcome["state"] == "awaiting-evidence"
    assert outcome["assessment"] == "evidence-incomplete"


def test_verify_skipped_evidence_keeps_confidence_limited() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="passed",
            run_id="verify-partial",
        ),
        repo_root=Path("/repo"),
        verification=_payload(
            schema="quality-runner-gate-verification-v0.1",
            status="passed",
            timeout_seconds=120,
            execute_discovered_gates=True,
            verification_context={
                "execution_authorized": True,
                "worktree_mode": "disposable",
                "mutations_isolated": True,
            },
            gates=[
                {"id": "tests", "status": "passed"},
                {
                    "id": "ci",
                    "status": "skipped",
                    "reason": "capability is CI-only and has no local executor",
                },
            ],
        ),
    )

    assert outcome["confidence"]["level"] == "limited"
    assert outcome["confidence"]["limitations"] == [
        "capability is CI-only and has no local executor"
    ]
    assert outcome["state"] == "awaiting-evidence"
    assert outcome["assessment"] == "evidence-incomplete"
    assert outcome["next_action"]["kind"] == "inspect-run"


def test_verify_policy_block_does_not_request_already_granted_consent() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="blocked",
            run_id="verify-policy",
        ),
        repo_root=Path("/repo"),
        verification=_payload(
            schema="quality-runner-gate-verification-v0.1",
            status="blocked",
            timeout_seconds=120,
            execute_discovered_gates=True,
            verification_context={
                "execution_authorized": True,
                "worktree_mode": "disposable",
                "mutations_isolated": True,
            },
            gates=[
                {
                    "id": "formatter",
                    "status": "skipped",
                    "skip_type": "mutating-gate-not-run",
                    "reason": "read-only gate policy skipped a possibly mutating command",
                }
            ],
        ),
    )

    assert outcome["safety"]["requires_explicit_authorization"] is False
    assert outcome["safety"]["mode"] == "evidence-only"
    assert outcome["next_action"]["kind"] == "inspect-gate-failure"


def test_empty_and_blocked_run_history_outcomes_are_truthful() -> None:
    empty = project_runs_outcome(
        {"repo_root": "/repo", "runs": [], "truncated": False, "unavailable_run_ids": []},
        repo_root=Path("/repo"),
    )
    blocked = project_runs_outcome(
        {
            "repo_root": "/repo",
            "runs": [{"run_id": "verify-003", "status": "blocked"}],
            "truncated": False,
            "unavailable_run_ids": [],
        },
        repo_root=Path("/repo"),
    )

    assert empty["state"] == "empty"
    assert empty["assessment"] == "no-history"
    assert empty["next_action"]["kind"] == "start-audit"
    assert blocked["state"] == "complete"
    assert blocked["assessment"] == "history"
    assert "blocked" in blocked["summary"]
    assert blocked["history"] == {
        "runs": [{"run_id": "verify-003", "status": "blocked"}],
        "truncated": False,
        "unavailable_run_ids": [],
    }


def test_unknown_historical_status_remains_limited_evidence() -> None:
    outcome = project_runs_outcome(
        {
            "repo_root": "/repo",
            "runs": [{"run_id": "partial-run", "status": "unknown"}],
            "truncated": False,
            "unavailable_run_ids": [],
        },
        repo_root=Path("/repo"),
    )

    assert outcome["state"] == "awaiting-evidence"
    assert outcome["confidence"]["level"] == "limited"
    assert outcome["next_action"]["kind"] == "inspect-run"


def test_unreadable_history_is_not_reported_as_no_history() -> None:
    outcome = project_runs_outcome(
        {
            "repo_root": "/repo",
            "runs": [],
            "selected_run_id": "missing-run",
            "truncated": False,
            "unavailable_run_ids": ["missing-run"],
        },
        repo_root=Path("/repo"),
    )

    assert outcome["state"] == "awaiting-evidence"
    assert outcome["assessment"] == "evidence-incomplete"
    assert outcome["next_action"]["kind"] == "inspect-run"
    assert outcome["next_action"]["command"] == "quality-runner runs /repo"


def test_review_with_unavailable_evidence_is_not_confirmed() -> None:
    outcome = project_review_outcome(
        _payload(
            schema="quality-runner-review-result-v0.1",
            status="review-complete",
            run_id="review-limited",
            report={"findings": []},
            evidence_unavailable=["missing critical file"],
        ),
        repo_root=Path("/repo"),
    )

    assert outcome["state"] == "complete"
    assert outcome["confidence"]["level"] == "limited"
    assert outcome["confidence"]["limitations"] == ["missing critical file"]


def test_outcome_renderer_leads_with_state_confidence_writes_safety_and_next_action() -> None:
    outcome = project_verify_outcome(
        _payload(
            schema="quality-runner-verify-gates-result-v0.1",
            status="blocked",
            run_id="verify-004",
        ),
        repo_root=Path("/repo"),
        verification=_payload(
            schema="quality-runner-gate-verification-v0.1",
            status="blocked",
            timeout_seconds=120,
            execute_discovered_gates=False,
            verification_context={"execution_authorized": False, "worktree_mode": "in-place"},
            gates=[],
        ),
    )

    assert render_outcome(outcome) == "\n".join(
        [
            "verify: blocked",
            "run id: verify-004",
            "assessment: evidence-incomplete",
            "confidence: limited — discovered gate plan",
            "writes: no new artifacts",
            "safety: evidence-only — No local gate command was executed; the recorded verification is evidence-only.",
            "next: Inspect blocked gate evidence before changing verification policy.",
            "limitations: No gate command was executed.",
            "command: quality-runner runs /repo --run-id verify-004",
        ]
    )


def _payload(**values: object) -> dict[str, object]:
    return values
