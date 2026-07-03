from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from quality_runner.schema_constants import GATE_VERIFICATION_SCHEMA

MAX_OUTPUT_CHARS = 4000
DEFAULT_TIMEOUT_SECONDS = 120


def verify_discovered_gates(
    *,
    repo_root: Path,
    capability_map: dict[str, Any],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    gates = [
        _verify_gate(repo_root=repo_root, capability=capability, timeout_seconds=timeout_seconds)
        for capability in _available_capabilities(capability_map)
    ]
    return {
        "schema": GATE_VERIFICATION_SCHEMA,
        "status": _status(gates),
        "timeout_seconds": timeout_seconds,
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
) -> dict[str, Any]:
    command = capability.get("command")
    capability_id = str(capability.get("id") or "unknown")
    if capability.get("local_execution") == "ci-only":
        return {
            "id": capability_id,
            "status": "skipped",
            "reason": "capability is CI-only and has no local executor",
            "source": _string_or_none(capability.get("source")),
        }
    if not isinstance(command, str) or not command:
        return {
            "id": capability_id,
            "status": "skipped",
            "reason": "capability has no executable command",
            "source": _string_or_none(capability.get("source")),
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
        return {
            "id": capability_id,
            "status": "failed",
            "command": command,
            "source": _string_or_none(capability.get("source")),
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": _truncate(error.stdout),
            "stderr": _truncate(error.stderr),
            "stdout_tail": _truncate(error.stdout),
            "stderr_tail": _truncate(error.stderr),
            "reason": "gate timed out",
        }
    stdout = _truncate(result.stdout)
    stderr = _truncate(result.stderr)
    return {
        "id": capability_id,
        "status": "passed" if result.returncode == 0 else "failed",
        "command": command,
        "source": _string_or_none(capability.get("source")),
        "exit_code": result.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout": stdout,
        "stderr": stderr,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
    }


def _available_capabilities(capability_map: dict[str, Any]) -> list[dict[str, Any]]:
    available = capability_map.get("available")
    if not isinstance(available, list):
        return []
    return [capability for capability in available if isinstance(capability, dict)]


def _status(gates: list[dict[str, Any]]) -> str:
    if any(gate.get("status") == "failed" for gate in gates):
        return "failed"
    if gates and all(gate.get("status") == "passed" for gate in gates):
        return "passed"
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
