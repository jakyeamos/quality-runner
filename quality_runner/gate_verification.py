from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from quality_runner.gate_execution_policy import (
    build_gate_execution_plan,
    failure_type,
    gate_cwd,
    mutating_risk,
    ordered_capabilities,
    recommended_action,
    timeout_diagnostics,
    valid_gate_timeouts,
)
from quality_runner.schema_constants import GATE_VERIFICATION_SCHEMA

MAX_OUTPUT_CHARS = 4000
DEFAULT_TIMEOUT_SECONDS = 120
AGGREGATE_GATE_IDS = {"pre_cr", "pre_pr"}
LEAF_GATE_IDS = ("formatter", "lint", "typecheck", "tests", "build", "dead_code", "runtime_smoke")


def verify_discovered_gates(
    *,
    repo_root: Path,
    capability_map: dict[str, Any],
    run_id: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    gate_timeouts: dict[str, int] | None = None,
    read_only_gates: bool = False,
    allow_mutating_gates: bool = False,
    on_partial_result: Any | None = None,
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    passed_leaf_ids: set[str] = set()
    resolved_gate_timeouts = valid_gate_timeouts(gate_timeouts)
    execution_plan = build_gate_execution_plan(
        repo_root=repo_root,
        capability_map=capability_map,
        timeout_seconds=timeout_seconds,
        gate_timeouts=resolved_gate_timeouts,
        read_only_gates=read_only_gates,
        allow_mutating_gates=allow_mutating_gates,
    )
    for capability in ordered_capabilities(capability_map):
        capability_id = str(capability.get("id") or "unknown")
        timeout = resolved_gate_timeouts.get(capability_id, timeout_seconds)
        gate = _verify_gate(
            repo_root=repo_root,
            capability=capability,
            timeout_seconds=timeout,
            covered_by=_covered_by(capability, passed_leaf_ids),
            read_only_gates=read_only_gates,
            allow_mutating_gates=allow_mutating_gates,
        )
        gates.append(gate)
        if capability_id in LEAF_GATE_IDS and gate.get("status") == "passed":
            passed_leaf_ids.add(capability_id)
        if on_partial_result is not None:
            on_partial_result(
                _verification_payload(
                    run_id=run_id,
                    gates=gates,
                    timeout_seconds=timeout_seconds,
                    gate_timeouts=resolved_gate_timeouts,
                    read_only_gates=read_only_gates,
                    allow_mutating_gates=allow_mutating_gates,
                    execution_plan=execution_plan,
                )
            )
    return _verification_payload(
        run_id=run_id,
        gates=gates,
        timeout_seconds=timeout_seconds,
        gate_timeouts=resolved_gate_timeouts,
        read_only_gates=read_only_gates,
        allow_mutating_gates=allow_mutating_gates,
        execution_plan=execution_plan,
    )


def _verification_payload(
    *,
    run_id: str | None,
    gates: list[dict[str, Any]],
    timeout_seconds: int,
    gate_timeouts: dict[str, int],
    read_only_gates: bool,
    allow_mutating_gates: bool,
    execution_plan: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": GATE_VERIFICATION_SCHEMA,
        **_optional_field("run_id", run_id),
        "status": _status(gates),
        "timeout_seconds": timeout_seconds,
        "gate_timeouts": gate_timeouts,
        "read_only_gates": read_only_gates,
        "allow_mutating_gates": allow_mutating_gates,
        "environment": _environment(),
        "execution_plan": execution_plan,
        "gates": gates,
    }


def apply_gate_verification(
    capability_map: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    results = {
        gate["id"]: gate
        for gate in verification.get("gates", [])
        if isinstance(gate, dict) and isinstance(gate.get("id"), str)
    }
    updated = dict(capability_map)
    available: list[dict[str, Any]] = []
    for capability in _available_capabilities(capability_map):
        copied = dict(capability)
        gate = results.get(str(copied.get("id")))
        if gate is not None and gate.get("status") in {"passed", "failed"}:
            previous = copied.get("verification_state")
            discovery = (
                previous.get("discovery")
                if isinstance(previous, dict) and isinstance(previous.get("discovery"), str)
                else _discovery_for_capability(copied)
            )
            copied["verification_state"] = {
                "discovery": discovery,
                "execution": "local-executed",
                "result": gate["status"],
            }
        available.append(copied)
    updated["available"] = available
    return updated


def _verify_gate(
    *,
    repo_root: Path,
    capability: dict[str, Any],
    timeout_seconds: int,
    covered_by: list[str],
    read_only_gates: bool,
    allow_mutating_gates: bool,
) -> dict[str, Any]:
    command = capability.get("command")
    capability_id = str(capability.get("id") or "unknown")
    capability_kind = _capability_kind(capability)
    source = _string_or_none(capability.get("source"))
    if capability.get("local_execution") == "ci-only":
        return {
            "id": capability_id,
            "status": "skipped",
            "capability_kind": "ci_only",
            "reason": "capability is CI-only and has no local executor",
            "source": source,
        }
    if capability_kind == "evidence_file":
        return {
            "id": capability_id,
            "status": "skipped",
            "capability_kind": capability_kind,
            "reason": "capability is file evidence, not an executable gate",
            "source": source,
        }
    if covered_by:
        return {
            "id": capability_id,
            "status": "skipped",
            "capability_kind": capability_kind,
            "reason": "aggregate gate covered by leaf gates",
            "source": source,
            "covered_by": covered_by,
        }
    if not isinstance(command, str) or not command:
        return {
            "id": capability_id,
            "status": "skipped",
            "capability_kind": capability_kind,
            "reason": "capability has no executable command",
            "source": source,
        }
    risk = mutating_risk(capability_id=capability_id, capability=capability)
    if (
        read_only_gates
        and not allow_mutating_gates
        and risk in {"mutating", "unknown"}
    ):
        return {
            "id": capability_id,
            "status": "skipped",
            "capability_kind": capability_kind,
            "command": command,
            "source": source,
            "cwd": str(gate_cwd(repo_root=repo_root, capability=capability)),
            "mutating_risk": risk,
            "skip_type": "mutating-gate-not-run",
            "reason": "read-only gate policy skipped a possibly mutating command",
            "recommended_action": "rerun with --allow-mutating-gates only when source changes are allowed",
        }

    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=repo_root,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        stdout = _truncate(error.stdout)
        stderr = _truncate(error.stderr)
        gate_failure_type = failure_type(
            command=command, stdout=stdout, stderr=stderr, timed_out=True
        )
        environment_restricted = gate_failure_type == "environment-restricted"
        dependency_setup = gate_failure_type == "dependency-setup-blocker"
        return {
            "id": capability_id,
            "status": "failed",
            "capability_kind": capability_kind,
            "command": command,
            "source": source,
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "timeout_seconds": timeout_seconds,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_tail": stdout,
            "stderr_tail": stderr,
            "failure_type": gate_failure_type,
            "reason": "gate timed out",
            "diagnostics": timeout_diagnostics(command=command, stdout=stdout, stderr=stderr),
            **recommended_action(
                environment_restricted=environment_restricted,
                dependency_setup=dependency_setup,
            ),
        }
    stdout = _truncate(result.stdout)
    stderr = _truncate(result.stderr)
    gate_failure_type = failure_type(command=command, stdout=stdout, stderr=stderr, timed_out=False)
    failed = result.returncode != 0
    environment_restricted = failed and gate_failure_type == "environment-restricted"
    dependency_setup = failed and gate_failure_type == "dependency-setup-blocker"
    return {
        "id": capability_id,
        "status": "passed" if result.returncode == 0 else "failed",
        "capability_kind": capability_kind,
        "command": command,
        "source": source,
        "exit_code": result.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timeout_seconds": timeout_seconds,
        "cwd": str(gate_cwd(repo_root=repo_root, capability=capability)),
        "mutating_risk": risk,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        **_optional_field("failure_type", gate_failure_type if failed else None),
        **recommended_action(
            environment_restricted=environment_restricted,
            dependency_setup=dependency_setup,
        ),
    }


def _available_capabilities(capability_map: dict[str, Any]) -> list[dict[str, Any]]:
    available = capability_map.get("available")
    if not isinstance(available, list):
        return []
    return [capability for capability in available if isinstance(capability, dict)]


def _status(gates: list[dict[str, Any]]) -> str:
    if any(
        gate.get("failure_type") in {"environment-restricted", "dependency-setup-blocker"}
        or gate.get("skip_type") == "mutating-gate-not-run"
        for gate in gates
    ):
        return "blocked"
    if any(gate.get("status") == "failed" for gate in gates):
        return "failed"
    if any(gate.get("status") == "passed" for gate in gates):
        return "passed"
    if gates and all(gate.get("status") == "skipped" for gate in gates):
        return "skipped-nonlocal"
    return "blocked"


def _discovery_for_capability(capability: dict[str, Any]) -> str:
    capability_type = capability.get("type")
    if capability_type == "script":
        return "script-discovered"
    if capability_type == "file":
        return "file-discovered"
    return "command-discovered"


def _truncate(value: object) -> str:
    text = value if isinstance(value, str) else ""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + "\n[truncated]\n"


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _capability_kind(capability: dict[str, Any]) -> str:
    kind = capability.get("capability_kind")
    if kind in {"local_command", "ci_only", "evidence_file"}:
        return str(kind)
    if capability.get("local_execution") == "ci-only":
        return "ci_only"
    if capability.get("type") == "file":
        return "evidence_file"
    return "local_command"


def _covered_by(capability: dict[str, Any], passed_leaf_ids: set[str]) -> list[str]:
    capability_id = str(capability.get("id") or "")
    command = capability.get("command")
    if capability_id not in AGGREGATE_GATE_IDS or not isinstance(command, str):
        return []
    covered = [gate_id for gate_id in LEAF_GATE_IDS if gate_id in passed_leaf_ids]
    if not covered:
        return []
    if capability_id in AGGREGATE_GATE_IDS:
        return covered
    if any(_command_mentions_gate(command, gate_id) for gate_id in covered):
        return covered
    return []


def _command_mentions_gate(command: str, gate_id: str) -> bool:
    aliases = {
        "formatter": ("format", "fmt", "prettier"),
        "lint": ("lint",),
        "typecheck": ("typecheck", "type-check", "check-types"),
        "tests": ("test", "tests"),
        "build": ("build",),
        "dead_code": ("dead-code", "dead_code", "audit:dead-code", "knip", "vulture"),
        "runtime_smoke": ("smoke", "runtime-smoke", "smoke-test"),
    }.get(gate_id, ())
    normalized = command.lower()
    return any(alias in normalized for alias in aliases)


def _environment() -> dict[str, str | bool | None]:
    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "sandbox": None,
    }


def _optional_field(key: str, value: object) -> dict[str, Any]:
    if value is None:
        return {}
    return {key: value}
