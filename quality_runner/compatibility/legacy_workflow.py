from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from quality_runner.application.audit_workflows import inspect_payload, run_payload
from quality_runner.application.verification_workflows import verify_gates_payload
from quality_runner.artifacts import cleanup_artifacts
from quality_runner.config import load_repo_config
from quality_runner.core.audit_contracts import ScanExclusionOverlay
from quality_runner.progress import ProgressCallback
from quality_runner.refresh_workflow import resolve_analysis_cache_root, run_refresh_payload
from quality_runner.review_delta import build_review_delta, persist_review_delta
from quality_runner.run_summary import build_run_summary
from quality_runner.workflow_review_metadata import attach_review_metadata

PayloadCallback = Callable[..., dict[str, Any]]


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
    inspect_callback: PayloadCallback = inspect_payload,
    run_callback: PayloadCallback = run_payload,
    verify_callback: PayloadCallback = verify_gates_payload,
    summary_callback: PayloadCallback = build_run_summary,
    refresh_runner: Callable[..., dict[str, Any]] = run_refresh_payload,
    execute_discovered_gates: bool = False,
    agent_review_mode: str | None = None,
    scan_exclusion_overlay: ScanExclusionOverlay | None = None,
    readiness_evidence_file: Path | None = None,
    analysis_cache_root: Path | None = None,
    include_paths: tuple[str, ...] = (),
    progress: ProgressCallback | None = None,
    inspect_timeout_seconds: int | None = None,
    run_timeout_seconds: int | None = None,
    focus_paths: list[str] | None = None,
    cache_state: str = "not-configured",
    analysis_mode: str = "full",
    cache_mode: str = "repo",
    cache_root: Path | None = None,
    performance_budget_seconds: float | None = None,
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
    resolved_analysis_cache_root = resolve_analysis_cache_root(
        repo_root,
        execute_discovered_gates=execute_discovered_gates,
        analysis_cache_root=analysis_cache_root,
    )
    payload = refresh_runner(
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
        inspect_timeout_seconds=inspect_timeout_seconds,
        run_timeout_seconds=run_timeout_seconds,
        focus_paths=focus_paths,
        cache_state=cache_state,
        analysis_mode=analysis_mode,
        cache_mode=cache_mode,
        cache_root=cache_root,
        performance_budget_seconds=performance_budget_seconds,
        checkout_most_advanced_branch=checkout_most_advanced_branch,
        execute_discovered_gates=execute_discovered_gates,
        allow_mutating_gates=allow_mutating_gates,
        worktree_mode=worktree_mode,
        allow_dirty_worktree_verify=allow_dirty_worktree_verify,
        intent=intent,
        agent_review_mode=agent_review_mode,
        scan_exclusion_overlay=scan_exclusion_overlay,
        readiness_evidence_file=readiness_evidence_file,
        analysis_cache_root=resolved_analysis_cache_root,
        include_paths=include_paths,
        inspect_callback=inspect_callback,
        run_callback=run_callback,
        verify_callback=verify_callback,
        summary_callback=summary_callback,
        progress=progress,
    )
    if not review_enabled:
        _prune_completed_refresh_artifacts(
            repo_root=repo_root,
            run_ids={
                f"{run_id_prefix}-inspect",
                f"{run_id_prefix}-run",
                f"{run_id_prefix}-verify",
            },
        )
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
    attach_review_metadata(
        repo_root=repo_root,
        run_id=verify_run_id,
        cycle_id=review_cycle_id,
        iteration=review_iteration,
        baseline_run_id=baseline_run_id,
        delta_paths=delta_paths,
    )
    payload["review_delta"] = delta
    payload["review_delta_paths"] = delta_paths
    _prune_completed_refresh_artifacts(
        repo_root=repo_root,
        run_ids={
            f"{run_id_prefix}-inspect",
            f"{run_id_prefix}-run",
            f"{run_id_prefix}-verify",
        },
    )
    return payload


def _prune_completed_refresh_artifacts(*, repo_root: Path, run_ids: set[str]) -> None:
    try:
        cleanup_artifacts(
            repo_root,
            config=load_repo_config(repo_root),
            apply=True,
            preserve_run_ids=run_ids,
        )
    except (OSError, ValueError):
        return
