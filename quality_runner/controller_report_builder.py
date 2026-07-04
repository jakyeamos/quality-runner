from __future__ import annotations

from typing import Any

from quality_runner.controller_report_defaults import (
    controller_command_environment,
    controller_status_recommendation,
    inferred_blockers,
    repo_state,
)

CONTROLLER_REPORT_SCHEMA = "quality-runner-controller-report-v0.1"


def build_controller_report_from_summary(
    *,
    repo_path: str,
    branch_name: str,
    summary: dict[str, Any],
    baseline_run_id: str | None,
    git_status_short: str,
    files_changed: list[str] | None = None,
    verification: list[dict[str, str]] | None = None,
    blockers: list[str] | None = None,
    commit_hash: str | None = None,
    target_head: str | None = None,
    commit_created_by_task: bool = False,
    push_status: str = "not-pushed",
    ignored_generated_artifacts: list[str] | None = None,
    status: str | None = None,
    pre_head: str | None = None,
    pre_git_status_short: str | None = None,
    concurrency_note: str | None = None,
    report_path: str | None = None,
    generation_command: str | None = None,
) -> dict[str, Any]:
    final_qr = {
        "run_id": summary.get("run_id"),
        "status": summary.get("status"),
        "classification": summary.get("recommended_classification"),
        "blocker_classes": summary.get("blocker_classes", []),
        "artifact_path": summary.get("path"),
        "gate_verification_status": summary.get("gate_verification_status"),
        "audit_status": summary.get("audit_status"),
        "findings_total": _nested(summary, "finding_counts", "total"),
        "missing_capabilities": summary.get("missing_capabilities", []),
        "gate_results": summary.get("gate_results", []),
        "failure_type": summary.get("failure_type"),
        "timeout_diagnostics": summary.get("timeout_diagnostics"),
    }
    normalized_blockers = blockers if blockers else inferred_blockers(final_qr)
    recommendation = controller_status_recommendation(
        final_qr,
        commit_hash=commit_hash,
        commit_created_by_task=commit_created_by_task,
        push_status=push_status,
    )
    resolved_status = status or recommendation["status"]
    resolved_repo_state = repo_state(
        pre_head=pre_head or target_head,
        post_head=target_head,
        pre_git_status_short=pre_git_status_short,
        post_git_status_short=git_status_short,
        concurrency_note=concurrency_note,
    )
    return {
        "schema": CONTROLLER_REPORT_SCHEMA,
        "repo_path": repo_path,
        "branch_name": branch_name,
        "status": resolved_status,
        "controller_status_recommendation": recommendation,
        "baseline_artifact_path": _baseline_path(repo_path=repo_path, baseline_run_id=baseline_run_id)
        or str(summary.get("path") or ""),
        "final_qr": {key: value for key, value in final_qr.items() if value is not None},
        "files_changed": files_changed or [],
        "verification": verification
        or _controller_report_verification(
            repo_path=repo_path,
            run_id=str(summary.get("run_id") or ""),
            baseline_run_id=baseline_run_id,
            report_path=report_path,
            generation_command=generation_command,
            result=str(summary.get("status") or "unknown"),
        ),
        "commit_hash": commit_hash,
        "target_head": target_head,
        "commit_created_by_task": commit_created_by_task,
        "push_status": push_status,
        "git_status_short": git_status_short,
        "controller_command_environment": controller_command_environment(repo_path),
        "ignored_generated_artifacts": ignored_generated_artifacts
        or _default_ignored_generated_artifacts(git_status_short),
        "repo_state": resolved_repo_state,
        "blockers": normalized_blockers if resolved_status == "blocked" else blockers or [],
    }


def _controller_report_verification(
    *,
    repo_path: str,
    run_id: str,
    baseline_run_id: str | None,
    report_path: str | None,
    generation_command: str | None,
    result: str,
) -> list[dict[str, str]]:
    summarize_command = generation_command or _summarize_controller_report_command(
        repo_path=repo_path,
        run_id=run_id,
        baseline_run_id=baseline_run_id,
    )
    verification = [{"command": summarize_command, "result": result}]
    if report_path:
        verification.extend(
            [
                {
                    "command": f"quality-runner controller-report lint {report_path} --strict --json",
                    "result": "expected accepted",
                },
                {
                    "command": f"quality-runner validate-report {report_path} --json",
                    "result": "expected accepted",
                },
            ]
        )
    return verification


def _summarize_controller_report_command(
    *,
    repo_path: str,
    run_id: str,
    baseline_run_id: str | None,
) -> str:
    command = f"quality-runner summarize-run {repo_path} --run-id {run_id}"
    if baseline_run_id:
        command += f" --baseline-run-id {baseline_run_id}"
    return f"{command} --controller-report --json"


def _baseline_path(*, repo_path: str, baseline_run_id: str | None) -> str | None:
    if not repo_path or not baseline_run_id:
        return None
    return f"{repo_path.rstrip('/')}/.quality-runner/runs/{baseline_run_id}"


def _default_ignored_generated_artifacts(git_status: str) -> list[str]:
    return [".quality-runner/"] if ".quality-runner/" in git_status else []


def _nested(payload: dict[str, Any], key: str, nested_key: str) -> object:
    value = payload.get(key)
    return value.get(nested_key) if isinstance(value, dict) else None
