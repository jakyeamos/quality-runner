from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quality_runner.refresh_timeout import (
    build_timeout_verify_artifacts,
    not_started_refresh_phase,
    phase_timing,
    resolve_refresh_timeout_contract,
    timeout_refresh_phase,
    workflow_deadline,
)

PayloadCallback = Callable[..., dict[str, Any]]


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
    checkout_most_advanced_branch: bool,
    allow_mutating_gates: bool,
    inspect_callback: PayloadCallback,
    run_callback: PayloadCallback,
    verify_callback: PayloadCallback,
    summary_callback: PayloadCallback,
) -> dict[str, Any]:
    inspect_run_id = f"{run_id_prefix}-inspect"
    run_run_id = f"{run_id_prefix}-run"
    verify_run_id = f"{run_id_prefix}-verify"
    timeout_contract = resolve_refresh_timeout_contract(
        per_gate_timeout_seconds=timeout_seconds,
        workflow_timeout_seconds=workflow_timeout_seconds,
        verify_timeout_seconds=verify_timeout_seconds,
        workflow_timeout_reason=workflow_timeout_reason,
        total_timeout_seconds=total_timeout_seconds,
        total_timeout_reason=total_timeout_reason,
    )
    resolved_verify_timeout = timeout_contract["verify_timeout_seconds"]
    resolved_verify_reason = timeout_contract["verify_timeout_reason"]
    resolved_total_reason = timeout_contract["total_timeout_reason"]
    phase_timings: dict[str, dict[str, Any]] = {}
    total_started = time.monotonic()
    current = _RefreshTimeoutState(
        phase="inspect",
        phase_key="inspect",
        phase_started=total_started,
        timeout_seconds=total_timeout_seconds or resolved_verify_timeout,
        timeout_reason=resolved_total_reason or resolved_verify_reason,
        timeout_scope="total-refresh" if total_timeout_seconds is not None else "verify-phase",
    )
    inspect_result = not_started_refresh_phase(inspect_run_id, "inspect")
    run_result = not_started_refresh_phase(run_run_id, "run")

    def remaining_total_seconds() -> float | None:
        if total_timeout_seconds is None:
            return None
        return total_timeout_seconds - (time.monotonic() - total_started)

    def run_total_bounded_phase(
        *,
        phase: str,
        phase_key: str,
        callback: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        current.phase = phase
        current.phase_key = phase_key
        current.phase_started = time.monotonic()
        current.timeout_seconds = total_timeout_seconds or resolved_verify_timeout
        current.timeout_reason = resolved_total_reason or resolved_verify_reason
        current.timeout_scope = "total-refresh" if total_timeout_seconds is not None else "verify-phase"
        remaining = remaining_total_seconds()
        try:
            if remaining is None:
                result = callback()
            else:
                if remaining <= 0:
                    raise TimeoutError(current.timeout_reason)
                with workflow_deadline(seconds=remaining, reason=current.timeout_reason):
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
        inspect_result = run_total_bounded_phase(
            phase="inspect",
            phase_key="inspect",
            callback=lambda: inspect_callback(
                repo_root=repo_root,
                run_id=inspect_run_id,
                profile=profile,
                ci_status_json=ci_status_json,
                checkout_most_advanced_branch=checkout_most_advanced_branch,
            ),
        )
        run_result = run_total_bounded_phase(
            phase="run",
            phase_key="run",
            callback=lambda: run_callback(
                repo_root=repo_root,
                run_id=run_run_id,
                profile=profile,
                ci_status_json=ci_status_json,
                checkout_most_advanced_branch=checkout_most_advanced_branch,
            ),
        )
        verify_result = _run_verify_phase(
            repo_root=repo_root,
            run_id=verify_run_id,
            profile=profile,
            ci_status_json=ci_status_json,
            timeout_seconds=timeout_seconds,
            checkout_most_advanced_branch=checkout_most_advanced_branch,
            allow_mutating_gates=allow_mutating_gates,
            resolved_verify_timeout=resolved_verify_timeout,
            resolved_verify_reason=resolved_verify_reason,
            resolved_total_reason=resolved_total_reason,
            total_timeout_seconds=total_timeout_seconds,
            remaining_total_seconds=remaining_total_seconds,
            phase_timings=phase_timings,
            current=current,
            verify_callback=verify_callback,
        )
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
            elapsed_seconds=time.monotonic() - current.phase_started,
            baseline_run_id=baseline_run_id,
            timeout_scope=current.timeout_scope,
        )
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
    allow_mutating_gates: bool,
    resolved_verify_timeout: int,
    resolved_verify_reason: str,
    resolved_total_reason: str | None,
    total_timeout_seconds: int | None,
    remaining_total_seconds: Callable[[], float | None],
    phase_timings: dict[str, dict[str, Any]],
    current: _RefreshTimeoutState,
    verify_callback: PayloadCallback,
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
        current.timeout_seconds = total_timeout_seconds or resolved_verify_timeout
        current.timeout_reason = resolved_total_reason or resolved_verify_reason
        current.timeout_scope = "total-refresh"
    if verify_deadline <= 0:
        raise TimeoutError(current.timeout_reason)
    with workflow_deadline(seconds=verify_deadline, reason=current.timeout_reason):
        verify_result = verify_callback(
            repo_root=repo_root,
            run_id=run_id,
            profile=profile,
            ci_status_json=ci_status_json,
            timeout_seconds=timeout_seconds,
            checkout_most_advanced_branch=checkout_most_advanced_branch,
            read_only_gates=True,
            allow_mutating_gates=allow_mutating_gates,
        )
    phase_timings["verify"] = phase_timing(
        started=current.phase_started,
        status=str(verify_result.get("status", "completed")),
    )
    return verify_result


def _public_timeout_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "per_gate_timeout_seconds": contract["per_gate_timeout_seconds"],
        "verify_timeout_seconds": contract["verify_timeout_seconds"],
        "verify_timeout_source": contract["verify_timeout_source"],
        "total_timeout_seconds": contract["total_timeout_seconds"],
        "total_timeout_reason": contract["total_timeout_reason"],
    }
