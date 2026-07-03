from __future__ import annotations


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
