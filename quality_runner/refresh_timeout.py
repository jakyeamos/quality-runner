from __future__ import annotations

import json
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import Any

from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.manifest import build_run_manifest
from quality_runner.run_summary import build_run_summary
from quality_runner.schema_constants import GATE_VERIFICATION_SCHEMA

WORKFLOW_TIMEOUT_ARTIFACT_SCHEMA = "quality-runner-workflow-timeout-v0.1"


def default_workflow_timeout_seconds(per_gate_timeout_seconds: int) -> int:
    return max(per_gate_timeout_seconds * 3, per_gate_timeout_seconds + 60)


def timeout_reason(*, phase: str, timeout_seconds: int) -> str:
    return f"refresh workflow exceeded {timeout_seconds} seconds during {phase}"


@contextmanager
def workflow_deadline(*, seconds: int, reason: str) -> Iterator[None]:
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
) -> tuple[dict[str, Any], dict[str, Any]]:
    run_dir = prepare_artifact_dir(repo_root, run_id)
    plan_path = run_dir / "gate-execution-plan.json"
    verification_path = run_dir / "gate-verification.json"
    existing_plan = _existing_plan(plan_path)
    existing_verification = _existing_verification(verification_path)
    timeout_payload = {
        "schema": WORKFLOW_TIMEOUT_ARTIFACT_SCHEMA,
        "status": "blocked",
        "run_id": run_id,
        "phase": phase,
        "failure_type": "workflow-timeout",
        "reason": reason,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": round(elapsed_seconds, 3),
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
        "gates": _existing_gates(existing_verification),
    }
    artifact_paths = {
        "gate_execution_plan_json": str(run_dir / "gate-execution-plan.json"),
        "gate_verification_json": str(run_dir / "gate-verification.json"),
        "workflow_timeout_json": str(run_dir / "workflow-timeout.json"),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
        "run_summary_json": str(run_dir / "run-summary.json"),
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
