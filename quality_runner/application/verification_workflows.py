from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.application.gate_verification import run_gate_verification
from quality_runner.core.audit_contracts import AuditPayload
from quality_runner.core.verification_contracts import GateExecutionPolicy, VerificationRequest
from quality_runner.workflow_internal import generated_run_id


def verify_gates_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    timeout_seconds: int = 120,
    checkout_most_advanced_branch: bool = False,
    read_only_gates: bool = False,
    allow_mutating_gates: bool = False,
    worktree_mode: str = "in-place",
    allow_dirty_worktree_verify: bool = False,
    skill_review_report: AuditPayload | None = None,
    intent: AuditPayload | None = None,
    execute_discovered_gates: bool = False,
) -> dict[str, Any]:
    result = run_gate_verification(
        VerificationRequest(
            repo_root=repo_root,
            run_id=generated_run_id() if run_id is None else run_id,
            profile=profile,
            ci_status_json=ci_status_json,
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
        )
    )
    return {
        "schema": "quality-runner-verify-gates-result-v0.1",
        "status": result.status,
        "implementation_allowed": False,
        "run_id": result.run_id,
        "artifact_paths": result.artifact_paths,
        "warnings": list(result.warnings),
    }
