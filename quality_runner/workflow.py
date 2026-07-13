from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.application.audit_workflows import inspect_payload, run_payload
from quality_runner.application.verification_workflows import verify_gates_payload
from quality_runner.compatibility.legacy_workflow import refresh_payload as _refresh_payload
from quality_runner.refresh_workflow import run_refresh_payload
from quality_runner.run_summary import build_run_summary
from quality_runner.workflow_internal import generated_run_id

__all__ = [
    "generated_run_id",
    "inspect_payload",
    "refresh_payload",
    "run_payload",
    "verify_gates_payload",
]


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
    allow_mutating_gates: bool = False,
    worktree_mode: str = "in-place",
    allow_dirty_worktree_verify: bool = False,
    intent: dict[str, Any] | None = None,
    review_cycle_id: str | None = None,
    review_iteration: int | None = None,
    execute_discovered_gates: bool = False,
) -> dict[str, Any]:
    return _refresh_payload(
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
        review_cycle_id=review_cycle_id,
        review_iteration=review_iteration,
        inspect_callback=inspect_payload,
        run_callback=run_payload,
        verify_callback=verify_gates_payload,
        summary_callback=build_run_summary,
        refresh_runner=run_refresh_payload,
    )
