from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from quality_runner.application.audit_v1_artifacts import (
    plan_and_write_run_v1_artifacts,
    write_inspect_v1_artifacts,
)
from quality_runner.application.read_only_audit import analyze_read_only_audit
from quality_runner.artifacts import prepare_artifact_dir
from quality_runner.core.audit_contracts import AuditPayload, AuditRequest, AuditWarning
from quality_runner.git_branches import prepare_scan_branch
from quality_runner.workflow_helpers import combined_warnings
from quality_runner.workflow_internal import generated_run_id


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
