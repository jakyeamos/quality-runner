from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

ENVIRONMENT_RESTRICTED_MARKERS = (
    "eperm",
    "eacces",
    "permission denied",
    "operation not permitted",
    "listen eperm",
    "127.0.0.1",
    ".pipe",
    "socket",
    "failed to fetch",
    "fetch failed",
    "getaddrinfo",
    "econnreset",
    "enotfound",
    "next/font",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "google fonts",
    "network",
    "could not access",
)
DEPENDENCY_SETUP_MARKERS = (
    "err_pnpm_aborted_remove_modules_dir_no_tty",
    "err_pnpm_ignored_builds",
    "aborted_remove_modules_dir_no_tty",
    "ignored build scripts",
    "modules directory will be removed and reinstalled from scratch",
    "pnpm approve-builds",
)
TEST_SERVER_TIMEOUT_MARKERS = (
    "server is not running",
    "server not running",
    "failed to start server",
    "local server",
)
MUTATING_COMMAND_MARKERS = (
    "--fix",
    "--write",
    "eslint --fix",
    "prettier --write",
    "ruff format",
)


def build_gate_execution_plan(
    *,
    repo_root: Path,
    capability_map: dict[str, Any],
    timeout_seconds: int,
    gate_timeouts: dict[str, int] | None = None,
    read_only_gates: bool = False,
    allow_mutating_gates: bool = False,
) -> list[dict[str, Any]]:
    resolved_gate_timeouts = valid_gate_timeouts(gate_timeouts)
    plan: list[dict[str, Any]] = []
    for capability in ordered_capabilities(capability_map):
        capability_id = str(capability.get("id") or "unknown")
        command = capability.get("command")
        command_text = command if isinstance(command, str) else None
        cwd = gate_cwd(repo_root=repo_root, capability=capability)
        risk = mutating_risk(capability_id=capability_id, capability=capability)
        plan.append(
            {
                "id": capability_id,
                "command": command_text,
                "cwd": str(cwd),
                "source": _string_or_none(capability.get("source")),
                "capability_kind": _capability_kind(capability),
                "package_manager": package_manager_for_command(command_text),
                "mutating_risk": risk,
                "local_execution_status": local_execution_status(
                    capability=capability,
                    command=command_text,
                    mutating_risk=risk,
                    read_only_gates=read_only_gates,
                    allow_mutating_gates=allow_mutating_gates,
                ),
                "timeout_seconds": resolved_gate_timeouts.get(capability_id, timeout_seconds),
            }
        )
    return plan


def ordered_capabilities(capability_map: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(_available_capabilities(capability_map), key=_gate_cost_key)


def failure_type(*, command: str, stdout: str, stderr: str, timed_out: bool) -> str:
    combined = f"{command}\n{stdout}\n{stderr}".lower()
    if any(marker in combined for marker in DEPENDENCY_SETUP_MARKERS):
        return "dependency-setup-blocker"
    if any(marker in combined for marker in ENVIRONMENT_RESTRICTED_MARKERS):
        return "environment-restricted"
    if _looks_like_qr_spawned_test_server_timeout(command=command, combined=combined):
        return "environment-restricted"
    if timed_out:
        return "timeout"
    return "command-failed"


def recommended_action(*, environment_restricted: bool, dependency_setup: bool) -> dict[str, Any]:
    if dependency_setup:
        return {
            "recommended_action": (
                "run the package-manager install/setup command directly in an interactive shell "
                "or approve dependency restoration before rerunning QR gates; for pnpm ignored "
                "build scripts, run pnpm approve-builds"
            )
        }
    if not environment_restricted:
        return {}
    return {
        "recommended_action": (
            "rerun the exact command directly from the repo root; if it passes, treat "
            "this as a QR runner environment mismatch and rerun outside sandbox or "
            "with explicit network/localhost permissions"
        )
    }


def local_execution_status(
    *,
    capability: dict[str, Any],
    command: str | None,
    mutating_risk: str,
    read_only_gates: bool,
    allow_mutating_gates: bool,
) -> str:
    if capability.get("local_execution") == "ci-only":
        return "ci-only-skipped"
    if _capability_kind(capability) == "evidence_file":
        return "evidence-only-skipped"
    if command is None:
        return "no-command-skipped"
    if read_only_gates and not allow_mutating_gates and mutating_risk in {"mutating", "unknown"}:
        return "mutating-skipped"
    return "will-execute"


def mutating_risk(*, capability_id: str, capability: dict[str, Any]) -> str:
    configured = capability.get("mutating_risk")
    if configured in {"safe", "unknown", "mutating"}:
        return str(configured)
    command = capability.get("command")
    command_text = command.lower() if isinstance(command, str) else ""
    if any(marker in command_text for marker in ("--check", "check-format", "--list-different")):
        return "safe"
    if any(marker in command_text for marker in MUTATING_COMMAND_MARKERS):
        return "mutating"
    if capability_id == "pre_cr" and "pre-cr run --workspace" in command_text:
        return "unknown"
    if capability_id == "formatter":
        return "unknown"
    return "safe"


def gate_cwd(*, repo_root: Path, capability: dict[str, Any]) -> Path:
    cwd = capability.get("cwd")
    if isinstance(cwd, str) and cwd:
        return (repo_root / cwd).resolve()
    return repo_root


def package_manager_for_command(command: str | None) -> str | None:
    if command is None:
        return None
    normalized = command.strip().lower()
    for manager in ("pnpm", "npm", "yarn", "bun"):
        if normalized.startswith(f"{manager} ") or f"&& {manager} " in normalized:
            return manager
    return None


def valid_gate_timeouts(gate_timeouts: dict[str, int] | None) -> dict[str, int]:
    if not isinstance(gate_timeouts, dict):
        return {}
    return {
        gate_id: seconds
        for gate_id, seconds in gate_timeouts.items()
        if isinstance(gate_id, str) and gate_id and isinstance(seconds, int) and seconds > 0
    }


def timeout_diagnostics(*, command: str, stdout: str, stderr: str) -> dict[str, Any]:
    return {
        "timed_out": True,
        "command": command,
        "captured_stdout_chars": len(stdout),
        "captured_stderr_chars": len(stderr),
        "process_snapshot": _process_snapshot(command),
    }


def _looks_like_qr_spawned_test_server_timeout(*, command: str, combined: str) -> bool:
    lowered_command = command.lower()
    if "test" not in lowered_command:
        return False
    has_timeout = "timed out" in combined or "timeout" in combined
    has_server_marker = any(marker in combined for marker in TEST_SERVER_TIMEOUT_MARKERS)
    return has_timeout and has_server_marker


def _available_capabilities(capability_map: dict[str, Any]) -> list[dict[str, Any]]:
    available = capability_map.get("available")
    if not isinstance(available, list):
        return []
    return [capability for capability in available if isinstance(capability, dict)]


def _gate_cost_key(capability: dict[str, Any]) -> tuple[int, str]:
    capability_id = str(capability.get("id") or "")
    if (
        _capability_kind(capability) == "evidence_file"
        or capability.get("local_execution") == "ci-only"
    ):
        cost = 95
    else:
        cost = {
            "formatter": 10,
            "lint": 20,
            "typecheck": 30,
            "runtime_smoke": 40,
            "dead_code": 50,
            "tests": 60,
            "build": 70,
            "pre_cr": 80,
            "pre_pr": 90,
        }.get(capability_id, 45)
    return cost, capability_id


def _capability_kind(capability: dict[str, Any]) -> str:
    kind = capability.get("capability_kind")
    if kind in {"local_command", "ci_only", "evidence_file"}:
        return str(kind)
    if capability.get("local_execution") == "ci-only":
        return "ci_only"
    if capability.get("type") == "file":
        return "evidence_file"
    return "local_command"


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _process_snapshot(command: str) -> str:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid,ppid,stat,command"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    needle = command.split()[0] if command.split() else command
    lines = [
        line
        for line in result.stdout.splitlines()
        if needle and needle in line and "quality-runner" not in line
    ]
    return "\n".join(lines[-20:])
