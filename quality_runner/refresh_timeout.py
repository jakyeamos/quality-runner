from __future__ import annotations

import json
import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import Any

from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.manifest import build_run_manifest
from quality_runner.planning import build_agent_handoff, render_handoff_markdown
from quality_runner.run_summary import build_run_summary
from quality_runner.scan_exclusions import scan_progress_snapshot
from quality_runner.schema_constants import GATE_VERIFICATION_SCHEMA
from quality_runner.timeout_diagnostics import (
    concise_timeout_diagnostics,
    timeout_diagnostics_payload,
    timeout_recommended_action,
)

WORKFLOW_TIMEOUT_ARTIFACT_SCHEMA = "quality-runner-workflow-timeout-v0.1"


def default_workflow_timeout_seconds(per_gate_timeout_seconds: int) -> int:
    return max(per_gate_timeout_seconds * 3, per_gate_timeout_seconds + 60)


def timeout_reason(*, phase: str, timeout_seconds: int) -> str:
    return f"refresh workflow exceeded {timeout_seconds} seconds during {phase}"


def resolve_refresh_timeout_contract(
    *,
    per_gate_timeout_seconds: int,
    workflow_timeout_seconds: int | None,
    verify_timeout_seconds: int | None,
    workflow_timeout_reason: str | None,
    total_timeout_seconds: int | None,
    total_timeout_reason: str | None,
) -> dict[str, Any]:
    if (
        workflow_timeout_seconds is not None
        and verify_timeout_seconds is not None
        and workflow_timeout_seconds != verify_timeout_seconds
    ):
        raise ValueError(
            "--workflow-timeout-seconds and --verify-timeout-seconds must match when both are set"
        )
    resolved_verify_timeout = (
        verify_timeout_seconds
        if verify_timeout_seconds is not None
        else workflow_timeout_seconds
        if workflow_timeout_seconds is not None
        else default_workflow_timeout_seconds(per_gate_timeout_seconds)
    )
    resolved_total_reason = (
        total_timeout_reason
        if total_timeout_reason is not None
        else (
            f"refresh exceeded {total_timeout_seconds} seconds across inspect, run, and verify"
            if total_timeout_seconds is not None
            else None
        )
    )
    return {
        "per_gate_timeout_seconds": per_gate_timeout_seconds,
        "verify_timeout_seconds": resolved_verify_timeout,
        "verify_timeout_source": (
            "explicit"
            if verify_timeout_seconds is not None or workflow_timeout_seconds is not None
            else "default"
        ),
        "verify_timeout_reason": workflow_timeout_reason
        or timeout_reason(phase="verify-gates", timeout_seconds=resolved_verify_timeout),
        "total_timeout_seconds": total_timeout_seconds,
        "total_timeout_reason": resolved_total_reason,
    }


def phase_timing(*, started: float, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def not_started_refresh_phase(run_id: str, phase: str) -> dict[str, Any]:
    return {
        "schema": "quality-runner-refresh-phase-result-v0.1",
        "status": "not-started",
        "implementation_allowed": False,
        "run_id": run_id,
        "phase": phase,
    }


def timeout_refresh_phase(
    *,
    run_id: str,
    phase: str,
    reason: str,
    timeout_seconds: int,
    timeout_scope: str,
) -> dict[str, Any]:
    return {
        "schema": "quality-runner-refresh-phase-result-v0.1",
        "status": "blocked",
        "implementation_allowed": False,
        "run_id": run_id,
        "phase": phase,
        "failure_type": "workflow-timeout",
        "reason": reason,
        "timeout_seconds": timeout_seconds,
        "timeout_scope": timeout_scope,
    }


@contextmanager
def workflow_deadline(*, seconds: int | float, reason: str) -> Iterator[None]:
    if seconds <= 0:
        yield
        return

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, 0)

    def _raise_timeout(_signum: int, _frame: FrameType | None) -> None:
        raise TimeoutError(reason)

    try:
        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])


def build_timeout_verify_artifacts(
    *,
    repo_root: Path,
    run_id: str,
    phase: str,
    reason: str,
    timeout_seconds: int,
    elapsed_seconds: float,
    baseline_run_id: str | None,
    timeout_scope: str = "verify-phase",
    phase_elapsed_seconds: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_dir = prepare_artifact_dir(repo_root, run_id)
    plan_path = run_dir / "gate-execution-plan.json"
    verification_path = run_dir / "gate-verification.json"
    existing_plan = _existing_plan(plan_path)
    existing_verification = _existing_verification(verification_path)
    diagnostics = _timeout_diagnostics()
    timeout_payload = {
        "schema": WORKFLOW_TIMEOUT_ARTIFACT_SCHEMA,
        "status": "blocked",
        "run_id": run_id,
        "phase": phase,
        "failure_type": "workflow-timeout",
        "reason": reason,
        "timeout_seconds": timeout_seconds,
        "timeout_scope": timeout_scope,
        "elapsed_seconds": round(elapsed_seconds, 3),
        **_optional_seconds("phase_elapsed_seconds", phase_elapsed_seconds),
        "diagnostics": diagnostics,
    }
    gate_verification = {
        **existing_verification,
        "schema": GATE_VERIFICATION_SCHEMA,
        "run_id": run_id,
        "status": "blocked",
        "timeout_seconds": timeout_seconds,
        "failure_type": "workflow-timeout",
        "phase": phase,
        "reason": reason,
        "elapsed_seconds": round(elapsed_seconds, 3),
        **_optional_seconds("phase_elapsed_seconds", phase_elapsed_seconds),
        "timeout_scope": timeout_scope,
        "diagnostics": diagnostics,
        "gates": _existing_gates(existing_verification)
        or [
            _workflow_timeout_gate(
                phase=phase,
                reason=reason,
                timeout_seconds=timeout_seconds,
                timeout_payload=timeout_payload,
            )
        ],
    }
    artifact_paths = {
        "gate_execution_plan_json": str(run_dir / "gate-execution-plan.json"),
        "gate_verification_json": str(run_dir / "gate-verification.json"),
        "workflow_timeout_json": str(run_dir / "workflow-timeout.json"),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
        "run_summary_json": str(run_dir / "run-summary.json"),
        "agent_handoff_json": str(run_dir / "agent-handoff.json"),
        "agent_handoff_md": str(run_dir / "agent-handoff.md"),
    }
    write_text(run_dir / "gate-execution-plan.json", json.dumps(existing_plan, indent=2) + "\n")
    write_json(run_dir / "gate-verification.json", gate_verification)
    write_json(run_dir / "workflow-timeout.json", timeout_payload)
    write_json(
        run_dir / "run-manifest.json",
        build_run_manifest(
            repo_root=repo_root,
            run_id=run_id,
            mode="verify-gates",
            artifact_paths=artifact_paths,
        ),
    )
    summary = build_run_summary(
        repo_root=repo_root,
        run_id=run_id,
        baseline_run_id=baseline_run_id,
    )
    handoff = build_agent_handoff(
        audit_report=_timeout_audit_report(run_id),
        remediation_plan=_timeout_remediation_plan(run_id),
        artifact_paths=artifact_paths,
        capability_map=_timeout_capability_map(),
        gate_verification=gate_verification,
    )
    write_json(run_dir / "agent-handoff.json", handoff)
    write_text(run_dir / "agent-handoff.md", render_handoff_markdown(handoff))
    verify_result = {
        "schema": "quality-runner-verify-gates-result-v0.1",
        "status": "blocked",
        "implementation_allowed": False,
        "run_id": run_id,
        "artifact_paths": artifact_paths,
        "timeout": timeout_payload,
        "warnings": [],
    }
    return verify_result, summary


def _workflow_timeout_gate(
    *,
    phase: str,
    reason: str,
    timeout_seconds: int,
    timeout_payload: dict[str, Any],
) -> dict[str, Any]:
    diagnostics = concise_timeout_diagnostics(timeout_payload)
    return {
        "id": "workflow-timeout",
        "status": "failed",
        "failure_type": "workflow-timeout",
        "phase": phase,
        "reason": reason,
        "timeout_diagnostics": diagnostics,
        "recommended_action": timeout_recommended_action(
            timeout_seconds=timeout_seconds,
            diagnostics=timeout_payload["diagnostics"],
        ),
    }


def _timeout_audit_report(run_id: str) -> dict[str, Any]:
    return {
        "schema": "quality-runner-audit-report-v0.1",
        "run_id": run_id,
        "status": "findings",
        "implementation_allowed": False,
        "findings": [],
    }


def _timeout_remediation_plan(run_id: str) -> dict[str, Any]:
    return {
        "schema": "quality-runner-remediation-plan-v0.1",
        "run_id": run_id,
        "implementation_allowed": False,
        "adoption_stage": {
            "id": "blocked-by-workflow-timeout",
            "title": "Blocked by workflow timeout",
            "rationale": "Refresh timed out before normal remediation planning completed.",
        },
        "stopping_criteria": ["Resolve the workflow timeout before implementation work."],
        "slices": [],
        "warnings": [],
    }


def _timeout_capability_map() -> dict[str, Any]:
    return {
        "schema": "quality-runner-capability-map-v0.1",
        "available": [],
        "missing": [],
        "warnings": [],
    }


def _timeout_diagnostics() -> dict[str, Any]:
    return timeout_diagnostics_payload(scan_progress_snapshot())


def _existing_plan(path: Path) -> list[Any]:
    payload = _read_existing_json(path)
    return payload if isinstance(payload, list) else []


def _existing_verification(path: Path) -> dict[str, Any]:
    payload = _read_existing_json(path)
    return payload if isinstance(payload, dict) else {}


def _existing_gates(verification: dict[str, Any]) -> list[Any]:
    gates = verification.get("gates")
    return gates if isinstance(gates, list) else []


def _read_existing_json(path: Path) -> object:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _optional_seconds(key: str, value: float | None) -> dict[str, float]:
    return {key: round(value, 3)} if value is not None else {}
