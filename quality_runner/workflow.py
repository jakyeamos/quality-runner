from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from quality_runner.application.audit_v1_artifacts import (
    plan_and_write_run_v1_artifacts,
    write_inspect_v1_artifacts,
)
from quality_runner.application.read_only_audit import analyze_read_only_audit
from quality_runner.artifacts import (
    existing_artifact_dir,
    prepare_artifact_dir,
    safe_child_file,
    write_json,
)
from quality_runner.core.audit_contracts import AuditPayload, AuditRequest, AuditWarning
from quality_runner.git_branches import prepare_scan_branch
from quality_runner.refresh_workflow import run_refresh_payload
from quality_runner.review_delta import build_review_delta, persist_review_delta
from quality_runner.run_summary import build_run_summary
from quality_runner.workflow_helpers import combined_warnings
from quality_runner.workflow_internal import generated_run_id
from quality_runner.workflow_verify import verify_gates_payload


def inspect_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    include_ignored_paths: list[str] | None = None,
    checkout_most_advanced_branch: bool = False,
    skill_review_report: AuditPayload | None = None,
    intent: AuditPayload | None = None,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    analysis = analyze_read_only_audit(
        _audit_request(
            repo_root=repo_root,
            run_id=resolved_run_id,
            profile=profile,
            ci_status_json=ci_status_json,
            include_ignored_paths=include_ignored_paths,
            branch_warnings=branch_warnings,
            skill_review_report=skill_review_report,
            intent=intent,
        )
    )
    artifact_paths = write_inspect_v1_artifacts(analysis, run_dir=run_dir)

    return {
        "schema": "quality-runner-inspect-result-v0.1",
        "status": "inspected",
        "implementation_allowed": False,
        "run_id": resolved_run_id,
        "artifact_paths": artifact_paths,
        "warnings": combined_warnings(
            _legacy_payload(analysis.scan), _legacy_payload(analysis.capability_map)
        ),
    }


def run_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    include_ignored_paths: list[str] | None = None,
    checkout_most_advanced_branch: bool = False,
    skill_review_report: AuditPayload | None = None,
    intent: AuditPayload | None = None,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    analysis = analyze_read_only_audit(
        _audit_request(
            repo_root=repo_root,
            run_id=resolved_run_id,
            profile=profile,
            ci_status_json=ci_status_json,
            include_ignored_paths=include_ignored_paths,
            branch_warnings=branch_warnings,
            skill_review_report=skill_review_report,
            intent=intent,
        )
    )
    planned, artifact_paths = plan_and_write_run_v1_artifacts(analysis, run_dir=run_dir)

    return {
        "schema": "quality-runner-run-result-v0.1",
        "status": planned.status,
        "implementation_allowed": False,
        "run_id": resolved_run_id,
        "artifact_paths": artifact_paths,
        "warnings": combined_warnings(
            _legacy_payload(analysis.scan), _legacy_payload(analysis.capability_map)
        ),
    }


def _audit_request(
    *,
    repo_root: Path,
    run_id: str,
    profile: str | None,
    ci_status_json: Path | None,
    include_ignored_paths: list[str] | None,
    branch_warnings: list[dict[str, str]],
    skill_review_report: AuditPayload | None,
    intent: AuditPayload | None,
) -> AuditRequest:
    return AuditRequest(
        repo_root=repo_root,
        run_id=run_id,
        profile=profile,
        ci_status_json=ci_status_json,
        include_ignored_paths=tuple(include_ignored_paths or []),
        branch_warnings=tuple(_audit_warning(warning) for warning in branch_warnings),
        skill_review_report=skill_review_report,
        intent=intent,
    )


def _audit_warning(warning: dict[str, str]) -> AuditWarning:
    return {
        "code": warning["code"],
        "message": warning["message"],
        "path": warning["path"],
    }


def _legacy_payload(payload: AuditPayload) -> dict[str, Any]:
    return cast(dict[str, Any], payload)


def refresh_payload(
    repo_root: Path,
    run_id_prefix: str,
    baseline_run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    timeout_seconds: int = 120,
    workflow_timeout_seconds: int | None = None,
    verify_timeout_seconds: int | None = None,
    workflow_timeout_reason: str | None = None,
    total_timeout_seconds: int | None = None,
    total_timeout_reason: str | None = None,
    checkout_most_advanced_branch: bool = False,
    execute_discovered_gates: bool = False,
    allow_mutating_gates: bool = False,
    worktree_mode: str = "in-place",
    allow_dirty_worktree_verify: bool = False,
    intent: dict[str, Any] | None = None,
    review_cycle_id: str | None = None,
    review_iteration: int | None = None,
) -> dict[str, Any]:
    review_enabled = review_cycle_id is not None or review_iteration is not None
    if review_enabled:
        if review_cycle_id is None or review_iteration is None:
            raise ValueError("--review-cycle-id and --review-iteration must be provided together")
        if intent is None or not isinstance(intent.get("goal"), str) or not intent["goal"].strip():
            raise ValueError("task intent is required for a review delta")
        assert review_cycle_id is not None
        assert review_iteration is not None
        assert intent is not None
    payload = run_refresh_payload(
        repo_root=repo_root,
        run_id_prefix=run_id_prefix,
        baseline_run_id=baseline_run_id,
        profile=profile,
        ci_status_json=ci_status_json,
        timeout_seconds=timeout_seconds,
        workflow_timeout_seconds=workflow_timeout_seconds,
        verify_timeout_seconds=verify_timeout_seconds,
        workflow_timeout_reason=workflow_timeout_reason,
        total_timeout_seconds=total_timeout_seconds,
        total_timeout_reason=total_timeout_reason,
        checkout_most_advanced_branch=checkout_most_advanced_branch,
        execute_discovered_gates=execute_discovered_gates,
        allow_mutating_gates=allow_mutating_gates,
        worktree_mode=worktree_mode,
        allow_dirty_worktree_verify=allow_dirty_worktree_verify,
        intent=intent,
        inspect_callback=inspect_payload,
        run_callback=run_payload,
        verify_callback=verify_gates_payload,
        summary_callback=build_run_summary,
    )
    if not review_enabled:
        return payload
    if review_cycle_id is None or review_iteration is None or intent is None:
        raise AssertionError("review metadata was unexpectedly cleared")
    verify_run_id = f"{run_id_prefix}-verify"
    delta = build_review_delta(
        repo_root=repo_root,
        run_id=verify_run_id,
        cycle_id=review_cycle_id,
        iteration=review_iteration,
        intent=intent,
        baseline_run_id=baseline_run_id,
    )
    delta_paths = persist_review_delta(repo_root=repo_root, run_id=verify_run_id, payload=delta)
    _attach_review_metadata(
        repo_root=repo_root,
        run_id=verify_run_id,
        cycle_id=review_cycle_id,
        iteration=review_iteration,
        baseline_run_id=baseline_run_id,
        delta_paths=delta_paths,
    )
    payload["review_delta"] = delta
    payload["review_delta_paths"] = delta_paths
    return payload


def _attach_review_metadata(
    *,
    repo_root: Path,
    run_id: str,
    cycle_id: str,
    iteration: int,
    baseline_run_id: str | None,
    delta_paths: dict[str, str],
) -> None:
    run_dir = existing_artifact_dir(repo_root, run_id)
    manifest_path = safe_child_file(run_dir, "run-manifest.json")
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["review_cycle"] = {
        "cycle_id": cycle_id,
        "iteration": iteration,
        "baseline_run_id": baseline_run_id,
        "artifact_paths": delta_paths,
    }
    write_json(manifest_path, manifest)
