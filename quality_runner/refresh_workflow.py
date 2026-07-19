from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quality_runner.core.audit_contracts import ScanExclusionOverlay
from quality_runner.progress import ProgressCallback, emit_progress
from quality_runner.refresh_timeout import (
    build_skipped_verify_artifacts,
    build_timeout_verify_artifacts,
    not_started_refresh_phase,
    phase_timing,
    resolve_refresh_timeout_contract,
    timeout_refresh_phase,
    workflow_deadline,
)
from quality_runner.refresh_timeout_context import timeout_context
from quality_runner.scan_exclusions import reset_scan_progress
from quality_runner.timeout_baseline import (
    load_gate_execution_plan,
    record_timeout_sample,
    resolve_timeout_context,
)

PayloadCallback = Callable[..., dict[str, Any]]


def resolve_analysis_cache_root(
    repo_root: Path,
    *,
    execute_discovered_gates: bool,
    analysis_cache_root: Path | None,
) -> Path | None:
    if execute_discovered_gates:
        return None
    return analysis_cache_root or repo_root.expanduser().resolve() / ".quality-runner"


def run_refresh_payload(
    *,
    repo_root: Path,
    run_id_prefix: str,
    baseline_run_id: str | None,
    profile: str | None,
    ci_status_json: Path | None,
    timeout_seconds: int,
    workflow_timeout_seconds: int | None,
    verify_timeout_seconds: int | None,
    workflow_timeout_reason: str | None,
    total_timeout_seconds: int | None,
    total_timeout_reason: str | None,
    inspect_timeout_seconds: int | None = None,
    run_timeout_seconds: int | None = None,
    checkout_most_advanced_branch: bool,
    execute_discovered_gates: bool = False,
    allow_mutating_gates: bool,
    worktree_mode: str = "in-place",
    allow_dirty_worktree_verify: bool = False,
    intent: dict[str, Any] | None,
    inspect_callback: PayloadCallback,
    run_callback: PayloadCallback,
    verify_callback: PayloadCallback,
    summary_callback: PayloadCallback,
    agent_review_mode: str | None = None,
    scan_exclusion_overlay: ScanExclusionOverlay | None = None,
    readiness_evidence_file: Path | None = None,
    focus_paths: list[str] | None = None,
    cache_state: str = "not-configured",
    analysis_cache_root: Path | None = None,
    analysis_mode: str = "full",
    cache_mode: str = "repo",
    cache_root: Path | None = None,
    performance_budget_seconds: float | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    inspect_run_id = f"{run_id_prefix}-inspect"
    run_run_id = f"{run_id_prefix}-run"
    verify_run_id = f"{run_id_prefix}-verify"
    adaptive_context = resolve_timeout_context(
        repo_root,
        profile=profile,
        per_gate_timeout_seconds=timeout_seconds,
        scan_exclusion_overlay=scan_exclusion_overlay,
        gate_plan=load_gate_execution_plan(repo_root, verify_run_id),
    )
    timeout_contract = resolve_refresh_timeout_contract(
        per_gate_timeout_seconds=timeout_seconds,
        workflow_timeout_seconds=workflow_timeout_seconds,
        verify_timeout_seconds=verify_timeout_seconds,
        workflow_timeout_reason=workflow_timeout_reason,
        total_timeout_seconds=total_timeout_seconds,
        total_timeout_reason=total_timeout_reason,
        inspect_timeout_seconds=inspect_timeout_seconds,
        run_timeout_seconds=run_timeout_seconds,
        adaptive=adaptive_context,
    )
    reset_scan_progress()
    refresh_context: dict[str, object] = {}
    resolved_verify_timeout = timeout_contract["verify_timeout_seconds"]
    resolved_verify_reason = timeout_contract["verify_timeout_reason"]
    resolved_total_reason = timeout_contract["total_timeout_reason"]
    resolved_inspect_timeout = timeout_contract["inspect_timeout_seconds"]
    resolved_run_timeout = timeout_contract["run_timeout_seconds"]
    resolved_total_timeout = timeout_contract["total_timeout_seconds"]
    phase_timings: dict[str, dict[str, Any]] = {}
    total_started = time.monotonic()
    current = _RefreshTimeoutState(
        phase="inspect",
        phase_key="inspect",
        phase_started=total_started,
        timeout_seconds=(
            resolved_total_timeout
            if resolved_total_timeout is not None
            else resolved_inspect_timeout
        ),
        timeout_reason=resolved_total_reason or resolved_verify_reason,
        timeout_scope="total-refresh" if resolved_total_timeout is not None else "phase",
    )
    inspect_result = not_started_refresh_phase(inspect_run_id, "inspect")
    run_result = not_started_refresh_phase(run_run_id, "run")
    summary: dict[str, Any] = {"status": "unknown"}

    def remaining_total_seconds() -> float | None:
        if resolved_total_timeout is None:
            return None
        return resolved_total_timeout - (time.monotonic() - total_started)

    def run_total_bounded_phase(
        *,
        phase: str,
        phase_key: str,
        callback: Callable[[], dict[str, Any]],
        phase_timeout_seconds: int,
    ) -> dict[str, Any]:
        current.phase = phase
        current.phase_key = phase_key
        current.phase_started = time.monotonic()
        current.timeout_seconds = phase_timeout_seconds
        phase_reason = f"refresh {phase} phase exceeded {phase_timeout_seconds} seconds"
        current.timeout_reason = phase_reason
        current.timeout_scope = "phase"
        remaining = remaining_total_seconds()
        try:
            effective_timeout = phase_timeout_seconds
            if remaining is not None:
                if remaining <= 0:
                    current.timeout_reason = resolved_total_reason or phase_reason
                    current.timeout_scope = "total-refresh"
                    raise TimeoutError(current.timeout_reason)
                effective_timeout = min(effective_timeout, remaining)
                if effective_timeout < phase_timeout_seconds:
                    current.timeout_reason = resolved_total_reason or phase_reason
                    current.timeout_scope = "total-refresh"
            with workflow_deadline(seconds=effective_timeout, reason=current.timeout_reason):
                result = callback()
        except TimeoutError:
            phase_timings[phase_key] = phase_timing(
                started=current.phase_started,
                status="timeout",
            )
            raise
        phase_timings[phase_key] = phase_timing(
            started=current.phase_started,
            status=str(result.get("status", "completed")),
        )
        return result

    try:
        emit_progress(progress, "refresh/inspect", f"run_id={inspect_run_id}")
        inspect_result = run_total_bounded_phase(
            phase="inspect",
            phase_key="inspect",
            callback=lambda: inspect_callback(
                repo_root=repo_root,
                run_id=inspect_run_id,
                profile=profile,
                ci_status_json=ci_status_json,
                readiness_evidence_file=readiness_evidence_file,
                checkout_most_advanced_branch=checkout_most_advanced_branch,
                agent_review_mode=agent_review_mode,
                scan_exclusion_overlay=scan_exclusion_overlay,
                intent=intent,
                analysis_cache_root=analysis_cache_root,
                refresh_context=refresh_context,
                focus_paths=focus_paths,
                analysis_mode=analysis_mode,
                cache_mode=cache_mode,
                cache_root=cache_root,
                performance_budget_seconds=performance_budget_seconds,
                progress=progress,
            ),
            phase_timeout_seconds=resolved_inspect_timeout,
        )
        emit_progress(progress, "refresh/run", f"run_id={run_run_id}")
        run_result = run_total_bounded_phase(
            phase="run",
            phase_key="run",
            callback=lambda: run_callback(
                repo_root=repo_root,
                run_id=run_run_id,
                profile=profile,
                ci_status_json=ci_status_json,
                readiness_evidence_file=readiness_evidence_file,
                checkout_most_advanced_branch=checkout_most_advanced_branch,
                agent_review_mode=agent_review_mode,
                scan_exclusion_overlay=scan_exclusion_overlay,
                intent=intent,
                analysis_cache_root=analysis_cache_root,
                refresh_context=refresh_context,
                focus_paths=focus_paths,
                analysis_mode=analysis_mode,
                cache_mode=cache_mode,
                cache_root=cache_root,
                performance_budget_seconds=performance_budget_seconds,
                progress=progress,
            ),
            phase_timeout_seconds=resolved_run_timeout,
        )
        emit_progress(progress, "refresh/verify-gates", f"run_id={verify_run_id}")
        run_manifest_path = (
            repo_root / ".quality-runner" / "runs" / run_run_id / "run-manifest.json"
        )
        if not execute_discovered_gates and not run_manifest_path.is_file():
            current.phase = "verify-gates"
            current.phase_key = "verify"
            current.phase_started = time.monotonic()
            verify_result = build_skipped_verify_artifacts(
                repo_root=repo_root,
                run_id=verify_run_id,
                reason=(
                    "refresh completed inspect/run callbacks without a run artifact; "
                    "gate verification was not started"
                ),
            )
            phase_timings["verify"] = phase_timing(
                started=current.phase_started,
                status="blocked",
            )
        else:
            verify_result = _run_verify_phase(
                repo_root=repo_root,
                run_id=verify_run_id,
                profile=profile,
                ci_status_json=ci_status_json,
                timeout_seconds=timeout_seconds,
                checkout_most_advanced_branch=checkout_most_advanced_branch,
                execute_discovered_gates=execute_discovered_gates,
                allow_mutating_gates=allow_mutating_gates,
                worktree_mode=worktree_mode,
                allow_dirty_worktree_verify=allow_dirty_worktree_verify,
                resolved_verify_timeout=resolved_verify_timeout,
                resolved_verify_reason=resolved_verify_reason,
                resolved_total_reason=resolved_total_reason,
                total_timeout_seconds=resolved_total_timeout,
                remaining_total_seconds=remaining_total_seconds,
                phase_timings=phase_timings,
                current=current,
                verify_callback=verify_callback,
                intent=intent,
                agent_review_mode=agent_review_mode,
                scan_exclusion_overlay=scan_exclusion_overlay,
                readiness_evidence_file=readiness_evidence_file,
                analysis_cache_root=analysis_cache_root,
                refresh_context=refresh_context,
                progress=progress,
            )
        emit_progress(progress, "refresh/summary", f"run_id={verify_run_id}")
        summary = summary_callback(
            repo_root=repo_root,
            run_id=verify_run_id,
            baseline_run_id=baseline_run_id,
        )
    except TimeoutError:
        phase_timings[current.phase_key] = phase_timing(
            started=current.phase_started,
            status="timeout",
        )
        if current.phase == "inspect":
            inspect_result = timeout_refresh_phase(
                run_id=inspect_run_id,
                phase="inspect",
                reason=current.timeout_reason,
                timeout_seconds=current.timeout_seconds,
                timeout_scope=current.timeout_scope,
            )
        elif current.phase == "run":
            run_result = timeout_refresh_phase(
                run_id=run_run_id,
                phase="run",
                reason=current.timeout_reason,
                timeout_seconds=current.timeout_seconds,
                timeout_scope=current.timeout_scope,
            )
        verify_result, summary = build_timeout_verify_artifacts(
            repo_root=repo_root,
            run_id=verify_run_id,
            phase=current.phase,
            reason=current.timeout_reason,
            timeout_seconds=current.timeout_seconds,
            elapsed_seconds=_timeout_elapsed_seconds(
                current=current,
                total_started=total_started,
            ),
            phase_elapsed_seconds=time.monotonic() - current.phase_started
            if current.timeout_scope == "total-refresh"
            else None,
            baseline_run_id=baseline_run_id,
            timeout_scope=current.timeout_scope,
            timeout_context=timeout_context(
                phase=current.phase,
                execute_discovered_gates=execute_discovered_gates,
                refresh_context=refresh_context,
                timeout_reason=current.timeout_reason,
            ),
        )
        timed_out = True
    else:
        timed_out = False

    baseline_recording = (
        {
            "status": "skipped",
            "reason": "timed-out refreshes cannot update the timeout baseline",
        }
        if timed_out
        else record_timeout_sample(
            repo_root,
            run_id_prefix=run_id_prefix,
            profile=profile,
            per_gate_timeout_seconds=timeout_seconds,
            phase_timings=phase_timings,
            summary=summary,
            execute_discovered_gates=execute_discovered_gates,
            scan_exclusion_overlay=scan_exclusion_overlay,
            timed_out=False,
            gate_plan=load_gate_execution_plan(repo_root, verify_run_id),
            focus_paths=focus_paths,
            cache_state=cache_state,
        )
    )
    timeout_contract["baseline_recording"] = baseline_recording
    if isinstance(baseline_recording, dict) and baseline_recording.get("status") == "recorded":
        timeout_contract["baseline_id"] = baseline_recording.get("baseline_id")
        timeout_contract["baseline_sample_count"] = baseline_recording.get("sample_count", 0)
        timeout_contract["baseline_status"] = baseline_recording.get("state")
        timeout_contract["baseline_identity_sha256"] = baseline_recording.get("identity_sha256")
    return {
        "schema": "quality-runner-refresh-result-v0.1",
        "status": summary["status"],
        "implementation_allowed": False,
        "run_id_prefix": run_id_prefix,
        "timeout_contract": _public_timeout_contract(timeout_contract),
        "phase_timings": phase_timings,
        "runs": {
            "inspect": inspect_result,
            "run": run_result,
            "verify": verify_result,
        },
        "summary": summary,
    }


class _RefreshTimeoutState:
    def __init__(
        self,
        *,
        phase: str,
        phase_key: str,
        phase_started: float,
        timeout_seconds: int,
        timeout_reason: str,
        timeout_scope: str,
    ) -> None:
        self.phase = phase
        self.phase_key = phase_key
        self.phase_started = phase_started
        self.timeout_seconds = timeout_seconds
        self.timeout_reason = timeout_reason
        self.timeout_scope = timeout_scope


def _run_verify_phase(
    *,
    repo_root: Path,
    run_id: str,
    profile: str | None,
    ci_status_json: Path | None,
    timeout_seconds: int,
    checkout_most_advanced_branch: bool,
    execute_discovered_gates: bool,
    allow_mutating_gates: bool,
    worktree_mode: str,
    allow_dirty_worktree_verify: bool,
    resolved_verify_timeout: int,
    resolved_verify_reason: str,
    resolved_total_reason: str | None,
    total_timeout_seconds: int | None,
    remaining_total_seconds: Callable[[], float | None],
    phase_timings: dict[str, dict[str, Any]],
    current: _RefreshTimeoutState,
    verify_callback: PayloadCallback,
    intent: dict[str, Any] | None,
    agent_review_mode: str | None,
    scan_exclusion_overlay: ScanExclusionOverlay | None,
    readiness_evidence_file: Path | None,
    analysis_cache_root: Path | None,
    refresh_context: dict[str, object],
    progress: ProgressCallback | None,
) -> dict[str, Any]:
    current.phase = "verify-gates"
    current.phase_key = "verify"
    current.phase_started = time.monotonic()
    verify_deadline = float(resolved_verify_timeout)
    current.timeout_seconds = resolved_verify_timeout
    current.timeout_reason = resolved_verify_reason
    current.timeout_scope = "verify-phase"
    remaining = remaining_total_seconds()
    if remaining is not None and remaining < verify_deadline:
        verify_deadline = remaining
        current.timeout_seconds = (
            total_timeout_seconds if total_timeout_seconds is not None else resolved_verify_timeout
        )
        current.timeout_reason = resolved_total_reason or resolved_verify_reason
        current.timeout_scope = "total-refresh"
    if verify_deadline <= 0:
        raise TimeoutError(current.timeout_reason)
    reset_scan_progress()
    with workflow_deadline(seconds=verify_deadline, reason=current.timeout_reason):
        emit_progress(progress, "verify-gates/execution", f"run_id={run_id}")
        verify_result = verify_callback(
            repo_root=repo_root,
            run_id=run_id,
            profile=profile,
            ci_status_json=ci_status_json,
            readiness_evidence_file=readiness_evidence_file,
            timeout_seconds=timeout_seconds,
            checkout_most_advanced_branch=checkout_most_advanced_branch,
            execute_discovered_gates=execute_discovered_gates,
            read_only_gates=True,
            allow_mutating_gates=allow_mutating_gates,
            worktree_mode=worktree_mode,
            allow_dirty_worktree_verify=allow_dirty_worktree_verify,
            agent_review_mode=agent_review_mode,
            scan_exclusion_overlay=scan_exclusion_overlay,
            intent=intent,
            analysis_cache_root=analysis_cache_root,
            refresh_context=refresh_context,
            progress=progress,
        )
    phase_timings["verify"] = phase_timing(
        started=current.phase_started,
        status=str(verify_result.get("status", "completed")),
    )
    return verify_result


def _timeout_elapsed_seconds(
    *,
    current: _RefreshTimeoutState,
    total_started: float,
) -> float:
    if current.timeout_scope == "total-refresh":
        return time.monotonic() - total_started
    return time.monotonic() - current.phase_started


def _public_timeout_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "per_gate_timeout_seconds": contract["per_gate_timeout_seconds"],
        "timeout_policy": contract["timeout_policy"],
        "source": contract["source"],
        "baseline_status": contract["baseline_status"],
        "baseline_reason": contract["baseline_reason"],
        "baseline_id": contract["baseline_id"],
        "baseline_path": contract["baseline_path"],
        "baseline_identity_sha256": contract["baseline_identity_sha256"],
        "baseline_sample_count": contract["baseline_sample_count"],
        "expected_gate_plan_sha256": contract["expected_gate_plan_sha256"],
        "baseline_recording": contract.get("baseline_recording"),
        "inspect_timeout_seconds": contract["inspect_timeout_seconds"],
        "inspect_timeout_source": contract["inspect_timeout_source"],
        "verify_timeout_seconds": contract["verify_timeout_seconds"],
        "verify_timeout_source": contract["verify_timeout_source"],
        "run_timeout_seconds": contract["run_timeout_seconds"],
        "run_timeout_source": contract["run_timeout_source"],
        "total_timeout_seconds": contract["total_timeout_seconds"],
        "total_timeout_source": contract["total_timeout_source"],
        "total_timeout_reason": contract["total_timeout_reason"],
    }
