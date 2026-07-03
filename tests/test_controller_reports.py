from __future__ import annotations

import json
from pathlib import Path


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


def test_controller_report_strict_lint_rejects_complete_without_task_commit() -> None:
    from quality_runner.controller_reports import lint_controller_report

    report = {
        "repo_path": "/repos/example",
        "branch_name": "qr/example",
        "status": "complete",
        "baseline_artifact_path": "/repos/example/.quality-runner/runs/baseline",
        "final_qr": {"run_id": "verify", "status": "passed", "classification": "clean"},
        "files_changed": ["package.json"],
        "verification": [{"command": "quality-runner summarize-run .", "result": "passed"}],
        "commit_hash": "abc1234",
        "commit_created_by_task": False,
        "push_status": "pushed",
        "git_status_short": "",
        "blockers": [],
    }

    result = lint_controller_report(report, strict=True)

    assert result["status"] == "rejected"
    assert "complete reports must set commit_created_by_task true" in result["errors"]


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
            "blocker_classes": ["workflow-timeout"],
            "gate_verification_status": "blocked",
            "audit_status": "findings",
            "finding_counts": {"total": 0},
            "missing_capabilities": [],
            "gate_results": [
                {
                    "id": "tests",
                    "status": "failed",
                    "failure_type": "command-failed",
                }
            ],
        },
        git_status_short="?? .quality-runner/",
        target_head="abc123",
        pre_head="abc123",
        report_path="/private/tmp/report.json",
    )

    result = validate_controller_report(report)

    assert report["status"] == "blocked"
    assert report["target_head"] == "abc123"
    assert report["commit_created_by_task"] is False
    assert report["repo_state"]["pre_head"] == "abc123"
    assert report["repo_state"]["dirty_state"] == {
        "pre_existing_dirty": [],
        "quality_runner_artifacts": ["?? .quality-runner/"],
        "post_command_artifacts": [],
    }
    assert report["final_qr"]["blocker_classes"] == ["workflow-timeout"]
    assert report["ignored_generated_artifacts"] == [".quality-runner/"]
    assert report["controller_status_recommendation"]["status"] == "blocked"
    assert report["controller_command_environment"] == {
        "UV_CACHE_DIR": "/repos/example/.quality-runner/cache/uv",
        "XDG_CACHE_HOME": "/repos/example/.quality-runner/cache/xdg",
    }
    assert report["blockers"] == [
        "Final QR is not clean: status=blocked; classification=workflow-timeout-blocker; blocker_classes=workflow-timeout.",
        "Failed gates: tests (command-failed).",
    ]
    assert report["verification"][-2:] == [
        {
            "command": "quality-runner controller-report lint /private/tmp/report.json --strict --json",
            "result": "expected accepted",
        },
        {
            "command": "quality-runner validate-report /private/tmp/report.json --json",
            "result": "expected accepted",
        },
    ]
    assert result["status"] == "accepted"


def test_controller_report_from_summary_groups_post_command_artifacts() -> None:
    from quality_runner.controller_reports import build_controller_report_from_summary

    report = build_controller_report_from_summary(
        repo_path="/repos/example",
        branch_name="qr/example",
        baseline_run_id="baseline",
        summary={
            "run_id": "verify",
            "path": "/repos/example/.quality-runner/runs/verify",
            "status": "blocked",
            "recommended_classification": "read-only-gate-blocker",
            "blocker_classes": ["read-only-policy"],
            "finding_counts": {"total": 0},
            "missing_capabilities": [],
        },
        pre_git_status_short=" M existing.txt",
        git_status_short=" M existing.txt\n?? .quality-runner/\n?? reports/generated.csv",
        target_head="abc123",
        pre_head="abc123",
    )

    assert report["repo_state"]["dirty_state"] == {
        "pre_existing_dirty": [" M existing.txt"],
        "quality_runner_artifacts": ["?? .quality-runner/"],
        "post_command_artifacts": ["?? reports/generated.csv"],
    }


def test_controller_report_promotes_timeout_diagnostics_from_summary() -> None:
    from quality_runner.controller_reports import build_controller_report_from_summary

    timeout_diagnostics = {
        "timeout_scope": "total-refresh",
        "reason": "controller full refresh budget",
        "last_directory": "CLFE/data/external/nba_pbp_cache",
        "visited_paths": 7728,
        "skipped_paths": 145,
        "visited_top_level_counts": {"CLFE": 5419},
        "skipped_top_level_counts": {"CLFE": 10},
        "pruning_recommendations": [
            {
                "kind": "scan-exclusion",
                "path": "CLFE/data/external/nba_pbp_cache",
                "pattern": "CLFE/data/external/nba_pbp_cache/**",
                "top_level": "CLFE",
                "top_level_visited_paths": 5419,
                "reason": "timeout ended inside a data/cache-like path after 7728 visited paths",
            }
        ],
    }

    report = build_controller_report_from_summary(
        repo_path="/repos/example",
        branch_name="qr/example",
        baseline_run_id="baseline",
        summary={
            "run_id": "verify",
            "path": "/repos/example/.quality-runner/runs/verify",
            "status": "blocked",
            "recommended_classification": "workflow-timeout-blocker",
            "blocker_classes": ["workflow-timeout"],
            "failure_type": "workflow-timeout",
            "finding_counts": {"total": 0},
            "missing_capabilities": [],
            "timeout_diagnostics": timeout_diagnostics,
        },
        git_status_short="",
        target_head="abc123",
        pre_head="abc123",
    )

    assert report["final_qr"]["timeout_diagnostics"] == timeout_diagnostics
    assert report["blockers"] == [
        "Final QR is not clean: status=blocked; classification=workflow-timeout-blocker; blocker_classes=workflow-timeout.",
        "Workflow timeout: total-refresh timed out at CLFE/data/external/nba_pbp_cache after 7728 visited paths.",
        "Suggested scan exclusion: CLFE/data/external/nba_pbp_cache/**.",
    ]


def test_controller_report_strict_lint_allows_head_change_with_note() -> None:
    from quality_runner.controller_reports import (
        build_controller_report_from_summary,
        lint_controller_report,
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
            "blocker_classes": ["workflow-timeout"],
            "finding_counts": {"total": 0},
            "missing_capabilities": [],
        },
        git_status_short="",
        target_head="def456",
        pre_head="abc123",
        concurrency_note="target owner advanced the branch during the evidence run",
    )

    result = lint_controller_report(report, strict=True)

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


def test_run_summary_reports_mixed_gate_blocker_classes(tmp_path: Path) -> None:
    from quality_runner.run_summary import build_run_summary

    run_dir = tmp_path / ".quality-runner" / "runs" / "mixed-verify"
    run_dir.mkdir(parents=True)
    (run_dir / "quality-audit.json").write_text(
        json.dumps({"status": "findings", "findings": []}),
        encoding="utf-8",
    )
    (run_dir / "capability-matrix.json").write_text(
        json.dumps({"missing": []}),
        encoding="utf-8",
    )
    (run_dir / "gate-verification.json").write_text(
        json.dumps(
            {
                "status": "blocked",
                "gates": [
                    {
                        "id": "formatter",
                        "status": "skipped",
                        "skip_type": "mutating-gate-not-run",
                    },
                    {
                        "id": "lint",
                        "status": "failed",
                        "failure_type": "command-failed",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = build_run_summary(repo_root=tmp_path, run_id="mixed-verify", persist=False)

    assert summary["recommended_classification"] == "mixed-gate-blocker"
    assert summary["blocker_classes"] == ["read-only-policy", "command-failure"]


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
