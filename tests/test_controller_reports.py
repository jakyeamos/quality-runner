from __future__ import annotations

import json


def test_controller_report_validation_rejects_completed_dirty_worktree() -> None:
    from quality_runner.controller_reports import validate_controller_report

    report = {
        "repo_path": "/repos/example",
        "branch_name": "qr/clean-audit-parallel-20260702T200935Z",
        "status": "complete",
        "baseline_artifact_path": "/repos/example/.quality-runner/runs/baseline",
        "final_qr": {"run_id": "final", "status": "clean"},
        "files_changed": ["package.json"],
        "verification": [{"command": "quality-runner verify-gates .", "result": "failed"}],
        "commit_hash": "abc1234",
        "push_status": "pushed",
        "git_status_short": " M package.json",
        "blockers": [],
    }

    result = validate_controller_report(report)

    assert result == {
        "schema": "quality-runner-controller-report-validation-v0.1",
        "status": "rejected",
        "errors": ["completed reports must have a clean git_status_short field"],
    }


def test_controller_report_validation_accepts_clean_blocked_report_without_commit() -> None:
    from quality_runner.controller_reports import validate_controller_report

    report = {
        "repo_path": "/repos/example",
        "branch_name": "qr/clean-audit-parallel-20260702T200935Z",
        "status": "blocked",
        "baseline_artifact_path": "/repos/example/.quality-runner/runs/baseline",
        "final_qr": {"run_id": "triage", "status": "blocked"},
        "files_changed": [],
        "verification": [{"command": "quality-runner run .", "result": "blocked"}],
        "commit_hash": None,
        "push_status": "not-pushed",
        "git_status_short": "",
        "blockers": ["missing repo dependency install"],
    }

    result = validate_controller_report(report)

    assert result == {
        "schema": "quality-runner-controller-report-validation-v0.1",
        "status": "accepted",
        "errors": [],
    }


def test_controller_report_normalizes_nested_worker_shape() -> None:
    from quality_runner.controller_reports import (
        normalize_controller_report,
        validate_controller_report,
    )

    report = {
        "schema": "repo-specific-report-v0.1",
        "status": "complete",
        "controller_context": {"branch": "codex/structural-scan-exclusions"},
        "target": {
            "repo_path": "/repos/tmcp",
            "git_status_short": "",
        },
        "baseline": {"requested_run_id": "parallel-tmcp"},
        "refresh": {"final_run_id": "refresh-tmcp-verify", "status": "passed-with-findings"},
        "final_qr": {
            "run_id": "refresh-tmcp-verify",
            "status": "passed-with-findings",
            "classification": "missing-capabilities",
        },
        "files_changed": {"tracked": []},
        "commit_push": {"commit": "not_performed", "push": "not_performed"},
        "blockers": [],
    }

    normalized = normalize_controller_report(report)
    result = validate_controller_report(normalized)

    assert normalized["repo_path"] == "/repos/tmcp"
    assert normalized["branch_name"] == "codex/structural-scan-exclusions"
    assert normalized["status"] == "ready-for-review"
    assert normalized["baseline_artifact_path"] == "/repos/tmcp/.quality-runner/runs/parallel-tmcp"
    assert normalized["final_qr"]["classification"] == "missing-capabilities"
    assert result["status"] == "accepted"


def test_controller_report_strict_lint_rejects_false_complete() -> None:
    from quality_runner.controller_reports import lint_controller_report

    report = {
        "repo_path": "/repos/example",
        "branch_name": "qr/example",
        "status": "complete",
        "baseline_artifact_path": "/repos/example/.quality-runner/runs/baseline",
        "final_qr": {
            "run_id": "verify",
            "status": "passed-with-findings",
            "classification": "missing-capabilities",
        },
        "files_changed": [],
        "verification": [{"command": "quality-runner summarize-run .", "result": "passed-with-findings"}],
        "commit_hash": None,
        "push_status": "not-pushed",
        "git_status_short": "",
        "blockers": [],
    }

    result = lint_controller_report(report, strict=True)

    assert result["status"] == "rejected"
    assert "complete reports must have final_qr status clean/passed" in result["errors"]


def test_controller_report_strict_lint_rejects_head_change_without_note() -> None:
    from quality_runner.controller_reports import lint_controller_report

    report = {
        "repo_path": "/repos/example",
        "branch_name": "qr/example",
        "status": "blocked",
        "baseline_artifact_path": "/repos/example/.quality-runner/runs/baseline",
        "final_qr": {"run_id": "verify", "status": "blocked"},
        "files_changed": [],
        "verification": [{"command": "quality-runner refresh .", "result": "blocked"}],
        "commit_hash": None,
        "push_status": "not-pushed",
        "git_status_short": "",
        "blockers": ["workflow-timeout"],
        "repo_state": {"pre_head": "abc123", "post_head": "def456"},
    }

    result = lint_controller_report(report, strict=True)

    assert result["status"] == "rejected"
    assert "reports with target HEAD changes must include an explicit concurrency note" in result["errors"]


def test_controller_report_from_summary_builds_valid_blocked_report() -> None:
    from quality_runner.controller_reports import (
        build_controller_report_from_summary,
        validate_controller_report,
    )

    report = build_controller_report_from_summary(
        repo_path="/repos/example",
        branch_name="qr/example",
        baseline_run_id="baseline",
        summary={
            "run_id": "verify",
            "path": "/repos/example/.quality-runner/runs/verify",
            "status": "blocked",
            "recommended_classification": "workflow-timeout-blocker",
            "gate_verification_status": "blocked",
            "audit_status": "findings",
            "finding_counts": {"total": 0},
            "missing_capabilities": [],
        },
        git_status_short="?? .quality-runner/",
    )

    result = validate_controller_report(report)

    assert report["status"] == "blocked"
    assert report["ignored_generated_artifacts"] == [".quality-runner/"]
    assert report["blockers"] == ["workflow-timeout-blocker"]
    assert result["status"] == "accepted"


def test_normalized_controller_report_is_json_serializable() -> None:
    from quality_runner.controller_reports import normalize_controller_report

    normalized = normalize_controller_report(
        {
            "run": {
                "target_repo": "/repos/example",
                "controller_branch": "codex/controller",
                "baseline_run_id_requested": "baseline",
                "command": "quality-runner refresh /repos/example",
                "exit_code": 0,
            },
            "quality_runner_result": {
                "final_run_id": "verify",
                "final_status": "blocked",
                "final_classification": "workflow-timeout-blocker",
            },
            "files_changed": {"tracked": []},
            "blockers": [{"detail": "workflow timeout"}],
            "git_status": {"after": {"all_short": "?? .quality-runner/"}},
        }
    )

    json.dumps(normalized)
    assert normalized["status"] == "blocked"


def test_controller_report_validation_accepts_ignored_generated_artifacts_for_completion() -> None:
    from quality_runner.controller_reports import validate_controller_report

    report = {
        "repo_path": "/repos/example",
        "branch_name": "qr/clean-audit-parallel-20260702T200935Z",
        "status": "complete",
        "baseline_artifact_path": "/repos/example/.quality-runner/runs/baseline",
        "final_qr": {"run_id": "final", "status": "clean"},
        "files_changed": ["package.json"],
        "verification": [{"command": "quality-runner verify-gates .", "result": "passed"}],
        "commit_hash": "abc1234",
        "push_status": "pushed",
        "git_status_short": "?? .quality-runner/",
        "ignored_generated_artifacts": [".quality-runner/"],
        "blockers": [],
    }

    result = validate_controller_report(report)

    assert result == {
        "schema": "quality-runner-controller-report-validation-v0.1",
        "status": "accepted",
        "errors": [],
    }
