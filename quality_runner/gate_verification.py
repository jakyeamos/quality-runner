from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from quality_runner.dependency_setup import (
    dependency_setup_context,
    dependency_setup_skipped_gate,
)
from quality_runner.gate_execution import verify_gate
from quality_runner.gate_execution_policy import (
    build_gate_execution_plan,
    ordered_capabilities,
    valid_gate_timeouts,
)
from quality_runner.gate_provenance import verification_provenance
from quality_runner.schema_constants import GATE_VERIFICATION_SCHEMA

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
    execute_discovered_gates: bool = False,
    read_only_gates: bool = False,
    allow_mutating_gates: bool = False,
    execution_root: Path | None = None,
    mutations_isolated: bool = False,
    verification_context: dict[str, Any] | None = None,
    on_partial_result: Any | None = None,
) -> dict[str, Any]:
    if execute_discovered_gates and (
        not mutations_isolated
        or execution_root is None
        or execution_root.expanduser().resolve() == repo_root.expanduser().resolve()
    ):
        raise ValueError("executing discovered gates requires a separate disposable execution root")
    gates: list[dict[str, Any]] = []
    passed_leaf_ids: set[str] = set()
    dependency_setup_blockers: dict[tuple[str, str], dict[str, Any]] = {}
    resolved_gate_timeouts = valid_gate_timeouts(gate_timeouts)
    execution_repo = execution_root or repo_root
    execution_plan = build_gate_execution_plan(
        repo_root=execution_repo,
        capability_map=capability_map,
        timeout_seconds=timeout_seconds,
        gate_timeouts=resolved_gate_timeouts,
        execute_discovered_gates=execute_discovered_gates,
        read_only_gates=read_only_gates,
        allow_mutating_gates=allow_mutating_gates,
        mutations_isolated=mutations_isolated,
    )
    for capability in ordered_capabilities(capability_map):
        capability_id = str(capability.get("id") or "unknown")
        timeout = resolved_gate_timeouts.get(capability_id, timeout_seconds)
        blocked_by_setup = dependency_setup_blockers.get(
            dependency_setup_context(repo_root=execution_repo, capability=capability)
        )
        if blocked_by_setup is None:
            gate = verify_gate(
                repo_root=execution_repo,
                capability=capability,
                timeout_seconds=timeout,
                covered_by=_covered_by(capability, passed_leaf_ids),
                execute_discovered_gates=execute_discovered_gates,
                read_only_gates=read_only_gates,
                allow_mutating_gates=allow_mutating_gates,
                mutations_isolated=mutations_isolated,
            )
        else:
            gate = dependency_setup_skipped_gate(
                repo_root=execution_repo,
                capability=capability,
                timeout_seconds=timeout,
                blocked_by=blocked_by_setup,
            )
        gates.append(gate)
        if capability_id in LEAF_GATE_IDS and gate.get("status") == "passed":
            passed_leaf_ids.add(capability_id)
        if (
            gate.get("failure_type") == "dependency-setup-blocker"
            and gate.get("status") == "failed"
        ):
            dependency_setup_blockers[
                dependency_setup_context(repo_root=execution_repo, capability=capability)
            ] = gate
        if on_partial_result is not None:
            on_partial_result(
                _verification_payload(
                    repo_root=repo_root,
                    run_id=run_id,
                    gates=gates,
                    timeout_seconds=timeout_seconds,
                    gate_timeouts=resolved_gate_timeouts,
                    execute_discovered_gates=execute_discovered_gates,
                    read_only_gates=read_only_gates,
                    allow_mutating_gates=allow_mutating_gates,
                    execution_plan=execution_plan,
                    verification_context=verification_context,
                )
            )
    return _verification_payload(
        repo_root=repo_root,
        run_id=run_id,
        gates=gates,
        timeout_seconds=timeout_seconds,
        gate_timeouts=resolved_gate_timeouts,
        execute_discovered_gates=execute_discovered_gates,
        read_only_gates=read_only_gates,
        allow_mutating_gates=allow_mutating_gates,
        execution_plan=execution_plan,
        verification_context=verification_context,
    )


def apply_gate_verification(
    capability_map: dict[str, Any], verification: dict[str, Any]
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
        if gate is not None and gate.get("status") in {"passed", "failed", "blocked"}:
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


def _verification_payload(
    *,
    repo_root: Path,
    run_id: str | None,
    gates: list[dict[str, Any]],
    timeout_seconds: int,
    gate_timeouts: dict[str, int],
    execute_discovered_gates: bool,
    read_only_gates: bool,
    allow_mutating_gates: bool,
    execution_plan: list[dict[str, Any]],
    verification_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": GATE_VERIFICATION_SCHEMA,
        **_optional_field("run_id", run_id),
        "status": _status(gates),
        "timeout_seconds": timeout_seconds,
        "gate_timeouts": gate_timeouts,
        "execute_discovered_gates": execute_discovered_gates,
        "read_only_gates": read_only_gates,
        "allow_mutating_gates": allow_mutating_gates,
        "environment": _environment(),
        "provenance": verification_provenance(
            repo_root=repo_root,
            run_id=run_id,
            gates=gates,
            verification_context=verification_context,
        ),
        "execution_plan": execution_plan,
        "gates": gates,
        **_optional_field("verification_context", verification_context),
    }


def verification_status(gates: list[dict[str, Any]]) -> str:
    return _status(gates)


def _available_capabilities(capability_map: dict[str, Any]) -> list[dict[str, Any]]:
    available = capability_map.get("available")
    if not isinstance(available, list):
        return []
    return [capability for capability in available if isinstance(capability, dict)]


def _status(gates: list[dict[str, Any]]) -> str:
    if any(
        gate.get("failure_type")
        in {"environment-restricted", "dependency-setup-blocker", "read-only-mutation"}
        or gate.get("skip_type") in {"mutating-gate-not-run", "execution-consent-required"}
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
    return {} if value is None else {key: value}
