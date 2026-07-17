from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from quality_runner.application.read_only_audit import analyze_read_only_audit, build_audit_plan
from quality_runner.application.verification_v1_artifacts import (
    prepare_verification_v1_artifacts,
    write_completed_verification_v1_artifacts,
    write_gate_execution_plan_v1,
    write_partial_gate_verification_v1,
)
from quality_runner.artifacts import prepare_artifact_dir
from quality_runner.core.audit_contracts import (
    AuditAnalysis,
    AuditPayload,
    AuditRequest,
    AuditWarning,
)
from quality_runner.core.verification_contracts import (
    GateExecutionPlan,
    GateVerificationPayload,
    VerificationRequest,
    VerificationResult,
)
from quality_runner.gate_verification import (
    apply_gate_verification,
    build_gate_execution_plan,
    verify_discovered_gates,
)
from quality_runner.git_branches import prepare_scan_branch
from quality_runner.unwired_from_dead_code import merge_dead_code_unwired_findings
from quality_runner.workflow_helpers import combined_warnings, gate_timeouts
from quality_runner.workflow_internal import verify_payload_status
from quality_runner.worktree_verify import gate_worktree_session, resolve_worktree_mode


def run_gate_verification(request: VerificationRequest) -> VerificationResult:
    resolved_worktree_mode = resolve_worktree_mode(request.policy.worktree_mode)
    if request.policy.execute_discovered_gates and resolved_worktree_mode != "disposable":
        raise ValueError(
            "executing discovered gates requires --worktree-mode disposable to isolate the target repository"
        )
    branch_warnings = prepare_scan_branch(
        request.repo_root,
        checkout_most_advanced_branch=request.checkout_most_advanced_branch,
    )
    run_dir = prepare_artifact_dir(request.repo_root, request.run_id)
    analysis = analyze_read_only_audit(_audit_request(request, branch_warnings))
    artifact_paths = prepare_verification_v1_artifacts(analysis, run_dir=run_dir)
    gate_execution_plan, gate_verification = _execute_discovered_gates(
        analysis=analysis,
        request=request,
        run_dir=run_dir,
        resolved_worktree_mode=resolved_worktree_mode,
    )
    verified_capability_map = _audit_payload(
        apply_gate_verification(
            _legacy_payload(analysis.capability_map), _legacy_payload(gate_verification)
        )
    )
    code_quality_scan = _audit_payload(
        merge_dead_code_unwired_findings(
            _legacy_payload(analysis.code_quality_scan),
            _legacy_payload(gate_verification),
            _legacy_payload(analysis.config),
        )
    )
    verified_analysis = replace(
        analysis,
        capability_map=verified_capability_map,
        code_quality_scan=code_quality_scan,
    )
    planned_audit = build_audit_plan(
        verified_analysis,
        artifact_paths=artifact_paths,
        gate_verification=_audit_payload(gate_verification),
    )
    artifact_paths = write_completed_verification_v1_artifacts(
        analysis=analysis,
        run_dir=run_dir,
        artifact_paths=artifact_paths,
        gate_execution_plan=gate_execution_plan,
        gate_verification=gate_verification,
        verified_capability_map=verified_capability_map,
        code_quality_scan=code_quality_scan,
        planned_audit=planned_audit,
    )
    return VerificationResult(
        run_id=request.run_id,
        status=verify_payload_status(
            _legacy_payload(gate_verification), _legacy_payload(planned_audit.remediation_plan)
        ),
        artifact_paths=artifact_paths,
        warnings=tuple(
            _audit_payload(warning)
            for warning in combined_warnings(
                _legacy_payload(analysis.scan), _legacy_payload(verified_capability_map)
            )
        ),
    )


def _execute_discovered_gates(
    *,
    analysis: AuditAnalysis,
    request: VerificationRequest,
    run_dir: Path,
    resolved_worktree_mode: str,
) -> tuple[GateExecutionPlan, GateVerificationPayload]:
    policy = request.policy
    effective_worktree_mode = (
        resolved_worktree_mode if policy.execute_discovered_gates else "in-place"
    )
    config = _legacy_payload(analysis.config)

    def write_partial_gate_verification(gate_verification: dict[str, Any]) -> None:
        write_partial_gate_verification_v1(
            run_dir=run_dir,
            gate_verification=_gate_verification_payload(gate_verification),
        )

    with gate_worktree_session(
        repo_root=request.repo_root,
        run_id=request.run_id,
        worktree_mode=effective_worktree_mode,
        allow_dirty_worktree_verify=policy.allow_dirty_worktree_verify,
    ) as worktree_session:
        verification_context = {
            **worktree_session.verification_context,
            "execution_authorized": policy.execute_discovered_gates,
        }
        gate_execution_plan = _gate_execution_plan(
            build_gate_execution_plan(
                repo_root=worktree_session.execution_root,
                capability_map=_legacy_payload(analysis.capability_map),
                timeout_seconds=policy.timeout_seconds,
                gate_timeouts=gate_timeouts(config),
                execute_discovered_gates=policy.execute_discovered_gates,
                read_only_gates=policy.read_only_gates,
                allow_mutating_gates=policy.allow_mutating_gates,
                mutations_isolated=worktree_session.mutations_isolated,
            )
        )
        write_gate_execution_plan_v1(run_dir=run_dir, gate_execution_plan=gate_execution_plan)
        gate_verification = _gate_verification_payload(
            verify_discovered_gates(
                repo_root=request.repo_root,
                capability_map=_legacy_payload(analysis.capability_map),
                run_id=request.run_id,
                timeout_seconds=policy.timeout_seconds,
                gate_timeouts=gate_timeouts(config),
                execute_discovered_gates=policy.execute_discovered_gates,
                read_only_gates=policy.read_only_gates,
                allow_mutating_gates=policy.allow_mutating_gates,
                execution_root=worktree_session.execution_root,
                mutations_isolated=worktree_session.mutations_isolated,
                verification_context=verification_context,
                on_partial_result=write_partial_gate_verification,
            )
        )
    return gate_execution_plan, gate_verification


def _audit_request(
    request: VerificationRequest,
    branch_warnings: list[dict[str, str]],
) -> AuditRequest:
    return AuditRequest(
        repo_root=request.repo_root,
        run_id=request.run_id,
        profile=request.profile,
        ci_status_json=request.ci_status_json,
        include_ignored_paths=(),
        branch_warnings=tuple(_audit_warning(warning) for warning in branch_warnings),
        skill_review_report=request.skill_review_report,
        intent=request.intent,
        scan_exclusion_overlay=request.scan_exclusion_overlay,
        agent_review_mode=request.agent_review_mode,
    )


def _audit_warning(warning: dict[str, str]) -> AuditWarning:
    return {
        "code": warning["code"],
        "message": warning["message"],
        "path": warning["path"],
    }


def _audit_payload(payload: dict[str, Any]) -> AuditPayload:
    return cast(AuditPayload, payload)


def _gate_execution_plan(payload: list[dict[str, Any]]) -> GateExecutionPlan:
    return cast(GateExecutionPlan, payload)


def _gate_verification_payload(payload: dict[str, Any]) -> GateVerificationPayload:
    return cast(GateVerificationPayload, payload)


def _legacy_payload(
    payload: AuditPayload | GateVerificationPayload,
) -> dict[str, Any]:
    return cast(dict[str, Any], payload)
