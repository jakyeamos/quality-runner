from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quality_runner.config import load_repo_config
from quality_runner.fleet.contracts import hash_text, redact_text
from quality_runner.process_runner import run_shell_command

ShellRunner = Callable[..., dict[str, Any]]


def aggregate_dynamic_status(statuses: list[str]) -> tuple[str, str | None]:
    """Prefer a decisive quality failure while retaining incomplete command receipts."""
    applicable = [status for status in statuses if status != "not_applicable"]
    if statuses and not applicable:
        return "not_applicable", "all discovered commands were excluded by read-only policy"
    if "failed" in applicable:
        return "failed", "one or more dynamic quality commands returned a failing result"
    if "timeout" in applicable:
        return "timeout", "one or more dynamic quality commands exceeded their bounded timeout"
    if "blocked" in applicable:
        return "blocked", "one or more dynamic quality commands were blocked by policy"
    if "unavailable" in applicable:
        return "unavailable", "one or more dynamic quality commands lacked a runtime prerequisite"
    if applicable and all(status == "passed" for status in applicable):
        return "passed", None
    return "unknown", None


def run_dynamic_command(
    command: dict[str, Any],
    worktree: Path,
    timeout_seconds: int,
    *,
    runner: ShellRunner = run_shell_command,
) -> dict[str, Any]:
    command_text = str(command.get("command", ""))
    try:
        result = runner(command_text, cwd=worktree, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        stdout = _output_text(error.output)
        stderr = _output_text(error.stderr)
        command_result = {
            "command_id": command.get("id"),
            "capability": command.get("id"),
            "status": "timeout",
            "timeout_seconds": timeout_seconds,
            "command_hash": hash_text(command_text),
            "command_source": command.get("source"),
            "stdout_length": len(stdout),
            "stderr_length": len(stderr),
            "reason": f"dynamic quality command exceeded its {timeout_seconds}-second timeout",
        }
        return command_result | _failure_output_tails(stdout, stderr, root=worktree)
    except TimeoutError:
        # The repository coordinator uses the built-in timeout signal. It must
        # reach the coordinator as a timeout rather than matching OSError below
        # and becoming an unavailable runtime prerequisite.
        raise
    except OSError as error:
        return {
            "command_id": command.get("id"),
            "capability": command.get("id"),
            "status": "unavailable",
            "reason": redact_text(str(error), root=worktree)[:500],
            "command_hash": hash_text(command_text),
            "command_source": command.get("source"),
            "timeout_seconds": timeout_seconds,
        }
    stdout = str(result.get("stdout", ""))
    stderr = str(result.get("stderr", ""))
    unavailable_reason = _missing_runtime_requirement(command_text, stdout, stderr)
    command_status = (
        "passed"
        if result.get("returncode") == 0
        else "unavailable"
        if unavailable_reason
        else "failed"
    )
    command_result = {
        "command_id": command.get("id"),
        "capability": command.get("id"),
        "status": command_status,
        "returncode": result.get("returncode"),
        "command_hash": hash_text(command_text),
        "command_source": command.get("source"),
        "timeout_seconds": timeout_seconds,
        "stdout_hash": hash_text(stdout),
        "stderr_hash": hash_text(stderr),
        "stdout_length": len(stdout),
        "stderr_length": len(stderr),
    }
    if unavailable_reason:
        command_result["reason"] = unavailable_reason
    if command_status != "passed":
        command_result.update(_failure_output_tails(stdout, stderr, root=worktree))
    return command_result


def configured_gate_timeouts(worktree: Path) -> dict[str, int]:
    try:
        configured = load_repo_config(worktree).get("gate_timeouts", {})
    except OSError:
        return {}
    if not isinstance(configured, dict):
        return {}
    return {
        str(capability_id): seconds
        for capability_id, seconds in configured.items()
        if isinstance(capability_id, str) and isinstance(seconds, int) and seconds > 0
    }


def command_timeout(
    capability_id: str, configured_gate_timeouts: dict[str, int], ceiling_seconds: int
) -> int:
    return min(configured_gate_timeouts.get(capability_id, ceiling_seconds), ceiling_seconds)


def safe_dynamic_command(command: dict[str, Any]) -> bool:
    if command.get("mutating_risk") in {"mutating", "unknown"}:
        return False
    text = str(command.get("command", "")).lower()
    if not text:
        return False
    if re.fullmatch(r"docker compose(?:\s+-f\s+[^\s]+)?\s+config", text):
        return True
    denied = (
        "install",
        "sync",
        "download",
        "curl ",
        "wget ",
        "git ",
        "docker",
        "vercel",
        "deploy",
        "push",
        "merge",
        "reset",
        "switch",
        "checkout",
        "rm ",
        "mv ",
        "cp ",
        "chmod",
        "--with",
        " >",
        ">>",
        "secret",
        "credential",
    )
    return not any(marker in text for marker in denied)


def dynamic_policy_block_reason(command: dict[str, Any]) -> str:
    risk = command.get("mutating_risk")
    if risk in {"mutating", "unknown"}:
        return (
            f"discovered command has {risk} mutation risk and cannot run in a read-only fleet audit"
        )
    return "command is outside the local read-only dynamic allowlist"


def _output_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _failure_output_tails(
    stdout: str, stderr: str, *, root: Path, limit: int = 4_000
) -> dict[str, str]:
    tails: dict[str, str] = {}
    if stdout:
        tails["stdout_tail"] = redact_text(stdout, root=root)[-limit:]
    if stderr:
        tails["stderr_tail"] = redact_text(stderr, root=root)[-limit:]
    return tails


def _missing_runtime_requirement(command: str, stdout: str, stderr: str) -> str | None:
    combined = f"{stdout}\n{stderr}".lower()
    if "golangci-lint" in combined and "no such file or directory" in combined:
        return "required executable golangci-lint is unavailable in the bounded runtime"
    if "command not found" in combined or "executable file not found" in combined:
        return "a required executable is unavailable in the bounded runtime"
    if "public agent-config engine not found" in combined:
        return "the documented public agent-config sibling runtime is unavailable"
    if "network connectivity is disabled" in combined and "wasn't found in the cache" in combined:
        return "a locked Python dependency is absent from the bounded offline cache"
    if (
        "econnrefused" in combined
        or "connection refused" in combined
        or "err_connection_refused" in combined
    ) and any(host in combined for host in ("127.0.0.1", "localhost", "::1")):
        return "the declared smoke check requires a local service that is not running"
    return None
