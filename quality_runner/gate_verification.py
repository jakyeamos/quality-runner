from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from quality_runner.schema_constants import GATE_VERIFICATION_SCHEMA

MAX_OUTPUT_CHARS = 4000
DEFAULT_TIMEOUT_SECONDS = 120
AGGREGATE_GATE_IDS = {"pre_cr", "pre_pr"}
LEAF_GATE_IDS = ("formatter", "lint", "typecheck", "tests", "build", "dead_code", "runtime_smoke")
ENVIRONMENT_RESTRICTED_MARKERS = (
    "eperm",
    "eacces",
    "permission denied",
    "operation not permitted",
    "listen eperm",
    "127.0.0.1",
    ".pipe",
    "socket",
)
TEST_SERVER_TIMEOUT_MARKERS = (
    "server is not running",
    "server not running",
    "failed to start server",
    "local server",
)


def verify_discovered_gates(
    *,
    repo_root: Path,
    capability_map: dict[str, Any],
    run_id: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    gate_timeouts: dict[str, int] | None = None,
) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    passed_leaf_ids: set[str] = set()
    resolved_gate_timeouts = _valid_gate_timeouts(gate_timeouts)
    for capability in _available_capabilities(capability_map):
        capability_id = str(capability.get("id") or "unknown")
        timeout = resolved_gate_timeouts.get(capability_id, timeout_seconds)
        gate = _verify_gate(
            repo_root=repo_root,
            capability=capability,
            timeout_seconds=timeout,
            covered_by=_covered_by(capability, passed_leaf_ids),
        )
        gates.append(gate)
        if capability_id in LEAF_GATE_IDS and gate.get("status") == "passed":
            passed_leaf_ids.add(capability_id)
    return {
        "schema": GATE_VERIFICATION_SCHEMA,
        **_optional_field("run_id", run_id),
        "status": _status(gates),
        "timeout_seconds": timeout_seconds,
        "gate_timeouts": resolved_gate_timeouts,
        "environment": _environment(),
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
        failure_type = _failure_type(command=command, stdout=stdout, stderr=stderr, timed_out=True)
        environment_restricted = failure_type == "environment-restricted"
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
            "failure_type": failure_type,
            "reason": "gate timed out",
            **_recommended_action(environment_restricted),
        }
    stdout = _truncate(result.stdout)
    stderr = _truncate(result.stderr)
    failure_type = _failure_type(command=command, stdout=stdout, stderr=stderr, timed_out=False)
    failed = result.returncode != 0
    environment_restricted = failed and failure_type == "environment-restricted"
    return {
        "id": capability_id,
        "status": "passed" if result.returncode == 0 else "failed",
        "capability_kind": capability_kind,
        "command": command,
        "source": source,
        "exit_code": result.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timeout_seconds": timeout_seconds,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        **_optional_field("failure_type", failure_type if failed else None),
        **_recommended_action(environment_restricted),
    }


def _available_capabilities(capability_map: dict[str, Any]) -> list[dict[str, Any]]:
    available = capability_map.get("available")
    if not isinstance(available, list):
        return []
    return [capability for capability in available if isinstance(capability, dict)]


def _status(gates: list[dict[str, Any]]) -> str:
    if any(gate.get("failure_type") == "environment-restricted" for gate in gates):
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


def _valid_gate_timeouts(gate_timeouts: dict[str, int] | None) -> dict[str, int]:
    if not isinstance(gate_timeouts, dict):
        return {}
    return {
        gate_id: seconds
        for gate_id, seconds in gate_timeouts.items()
        if isinstance(gate_id, str) and gate_id and isinstance(seconds, int) and seconds > 0
    }


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


def _failure_type(*, command: str, stdout: str, stderr: str, timed_out: bool) -> str:
    combined = f"{command}\n{stdout}\n{stderr}".lower()
    if any(marker in combined for marker in ENVIRONMENT_RESTRICTED_MARKERS):
        return "environment-restricted"
    if _looks_like_qr_spawned_test_server_timeout(command=command, combined=combined):
        return "environment-restricted"
    if timed_out:
        return "timeout"
    return "command-failed"


def _looks_like_qr_spawned_test_server_timeout(*, command: str, combined: str) -> bool:
    lowered_command = command.lower()
    if "test" not in lowered_command:
        return False
    has_timeout = "timed out" in combined or "timeout" in combined
    has_server_marker = any(marker in combined for marker in TEST_SERVER_TIMEOUT_MARKERS)
    return has_timeout and has_server_marker


def _recommended_action(environment_restricted: bool) -> dict[str, Any]:
    return _optional_field(
        "recommended_action",
        (
            "rerun the exact command directly from the repo root; if it passes, treat "
            "this as a QR runner environment mismatch and rerun outside sandbox or "
            "with explicit network/localhost permissions"
        )
        if environment_restricted
        else None,
    )


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
