from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.application.gate_verification import run_gate_verification
from quality_runner.core.audit_contracts import AuditAnalysis, AuditPayload, ScanExclusionOverlay
from quality_runner.core.verification_contracts import GateExecutionPolicy, VerificationRequest
from quality_runner.progress import ProgressCallback
from quality_runner.workflow_internal import generated_run_id


def verify_gates_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    readiness_evidence_file: Path | None = None,
    timeout_seconds: int = 120,
    checkout_most_advanced_branch: bool = False,
    read_only_gates: bool = False,
    allow_mutating_gates: bool = False,
    worktree_mode: str = "in-place",
    allow_dirty_worktree_verify: bool = False,
    skill_review_report: AuditPayload | None = None,
    intent: AuditPayload | None = None,
    execute_discovered_gates: bool = False,
    agent_review_mode: str | None = None,
    include_ignored_paths: list[str] | None = None,
    include_paths: tuple[str, ...] = (),
    scan_exclusion_overlay: ScanExclusionOverlay | None = None,
    progress: ProgressCallback | None = None,
    analysis_cache_root: Path | None = None,
    refresh_context: dict[str, object] | None = None,
) -> dict[str, Any]:
    analysis_override = (
        refresh_context.get("audit_analysis") if refresh_context is not None else None
    )
    result = run_gate_verification(
        VerificationRequest(
            repo_root=repo_root,
            run_id=generated_run_id() if run_id is None else run_id,
            profile=profile,
            ci_status_json=ci_status_json,
            readiness_evidence_file=readiness_evidence_file,
            checkout_most_advanced_branch=checkout_most_advanced_branch,
            policy=GateExecutionPolicy(
                timeout_seconds=timeout_seconds,
                execute_discovered_gates=execute_discovered_gates,
                read_only_gates=read_only_gates,
                allow_mutating_gates=allow_mutating_gates,
                worktree_mode=worktree_mode,
                allow_dirty_worktree_verify=allow_dirty_worktree_verify,
            ),
            skill_review_report=skill_review_report,
            intent=intent,
            scan_exclusion_overlay=scan_exclusion_overlay,
            include_ignored_paths=tuple(include_ignored_paths or []),
            include_paths=include_paths,
            agent_review_mode=agent_review_mode,
        ),
        analysis_override=(
            analysis_override if isinstance(analysis_override, AuditAnalysis) else None
        ),
        analysis_cache_root=analysis_cache_root,
        progress=progress,
    )
    return {
        "schema": "quality-runner-verify-gates-result-v0.1",
        "status": result.status,
        "implementation_allowed": False,
        "run_id": result.run_id,
        "artifact_paths": result.artifact_paths,
        "warnings": list(result.warnings),
    }
