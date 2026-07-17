from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from quality_runner.dependency_setup import dependency_setup_action, gate_diagnostics
from quality_runner.gate_execution_policy import (
    failure_type,
    gate_cwd,
    mutating_risk,
    recommended_action,
)
from quality_runner.gate_provenance import artifact_digest
from quality_runner.process_runner import run_shell_command
from quality_runner.read_only_git import TrackedSnapshot, restore_if_changed, tracked_snapshot

MAX_OUTPUT_CHARS = 4000


def verify_gate(
    *,
    repo_root: Path,
    capability: dict[str, Any],
    timeout_seconds: int,
    covered_by: list[str],
    execute_discovered_gates: bool,
    read_only_gates: bool,
    allow_mutating_gates: bool,
    mutations_isolated: bool = False,
) -> dict[str, Any]:
    command = capability.get("command")
    capability_id = str(capability.get("id") or "unknown")
    capability_kind = _capability_kind(capability)
    source = _string_or_none(capability.get("source"))
    skipped = _skipped_gate(
        repo_root=repo_root,
        capability=capability,
        capability_id=capability_id,
        capability_kind=capability_kind,
        command=command,
        source=source,
        covered_by=covered_by,
        execute_discovered_gates=execute_discovered_gates,
        read_only_gates=read_only_gates,
        allow_mutating_gates=allow_mutating_gates,
        mutations_isolated=mutations_isolated,
    )
    if skipped is not None:
        return skipped
    assert isinstance(command, str) and command
    risk = mutating_risk(capability_id=capability_id, capability=capability)
    return _execute_gate(
        repo_root=repo_root,
        capability=capability,
        capability_id=capability_id,
        capability_kind=capability_kind,
        command=command,
        source=source,
        risk=risk,
        timeout_seconds=timeout_seconds,
        read_only_gates=read_only_gates,
        allow_mutating_gates=allow_mutating_gates,
        mutations_isolated=mutations_isolated,
    )


def _skipped_gate(
    *,
    repo_root: Path,
    capability: dict[str, Any],
    capability_id: str,
    capability_kind: str,
    command: object,
    source: str | None,
    covered_by: list[str],
    execute_discovered_gates: bool,
    read_only_gates: bool,
    allow_mutating_gates: bool,
    mutations_isolated: bool,
) -> dict[str, Any] | None:
    if capability.get("local_execution") == "ci-only":
        return _base_skip(
            capability_id, "ci_only", source, "capability is CI-only and has no local executor"
        )
    if capability_kind in {"agent_review", "evidence"}:
        return _base_skip(
            capability_id,
            capability_kind,
            source,
            "capability is a review obligation or evidence signal, not an executable gate",
        )
    if capability_kind == "evidence_file":
        return _base_skip(
            capability_id,
            capability_kind,
            source,
            "capability is file evidence, not an executable gate",
        )
    if covered_by:
        return {
            **_base_skip(
                capability_id,
                capability_kind,
                source,
                "aggregate gate covered by leaf gates",
            ),
            "covered_by": covered_by,
        }
    if not isinstance(command, str) or not command:
        return _base_skip(
            capability_id, capability_kind, source, "capability has no executable command"
        )
    risk = mutating_risk(capability_id=capability_id, capability=capability)
    if not execute_discovered_gates:
        return {
            "id": capability_id,
            "status": "skipped",
            "capability_kind": capability_kind,
            "command": command,
            "source": source,
            "cwd": str(gate_cwd(repo_root=repo_root, capability=capability)),
            "mutating_risk": risk,
            "skip_type": "execution-consent-required",
            "reason": "Discovered command was recorded as evidence only and was not executed.",
            "recommended_action": (
                "Rerun with --execute-gates --worktree-mode disposable to execute discovered commands "
                "in a disposable checkout; this is not a sandbox."
            ),
        }
    if read_only_gates and not allow_mutating_gates and risk in {"mutating", "unknown"}:
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
            "recommended_action": (
                "rerun with --allow-mutating-gates only when changes in the disposable checkout "
                "are allowed"
            ),
        }
    return None


def _base_skip(
    capability_id: str, capability_kind: str, source: str | None, reason: str
) -> dict[str, Any]:
    return {
        "id": capability_id,
        "status": "skipped",
        "capability_kind": capability_kind,
        "reason": reason,
        "source": source,
    }


def _execute_gate(
    *,
    repo_root: Path,
    capability: dict[str, Any],
    capability_id: str,
    capability_kind: str,
    command: str,
    source: str | None,
    risk: str,
    timeout_seconds: int,
    read_only_gates: bool,
    allow_mutating_gates: bool,
    mutations_isolated: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    readonly_snapshot = (
        tracked_snapshot(repo_root)
        if read_only_gates and not allow_mutating_gates and not mutations_isolated
        else None
    )
    try:
        result = run_shell_command(command, cwd=repo_root, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        return _timeout_result(
            repo_root=repo_root,
            capability=capability,
            capability_id=capability_id,
            capability_kind=capability_kind,
            command=command,
            source=source,
            timeout_seconds=timeout_seconds,
            started=started,
            readonly_snapshot=readonly_snapshot,
            error=error,
        )
    return _completed_result(
        repo_root=repo_root,
        capability=capability,
        capability_id=capability_id,
        capability_kind=capability_kind,
        command=command,
        source=source,
        risk=risk,
        timeout_seconds=timeout_seconds,
        started=started,
        readonly_snapshot=readonly_snapshot,
        result=result,
    )


def _timeout_result(
    *,
    repo_root: Path,
    capability: dict[str, Any],
    capability_id: str,
    capability_kind: str,
    command: str,
    source: str | None,
    timeout_seconds: int,
    started: float,
    readonly_snapshot: TrackedSnapshot | None,
    error: subprocess.TimeoutExpired,
) -> dict[str, Any]:
    stdout = _truncate(error.stdout)
    stderr = _truncate(error.stderr)
    gate_failure_type = failure_type(command=command, stdout=stdout, stderr=stderr, timed_out=True)
    mutation = restore_if_changed(repo_root, readonly_snapshot)
    if mutation is not None:
        gate_failure_type = "read-only-mutation"
    environment_restricted = gate_failure_type == "environment-restricted"
    dependency_setup = gate_failure_type == "dependency-setup-blocker"
    diagnostics = (
        gate_diagnostics(
            command=command,
            cwd=gate_cwd(repo_root=repo_root, capability=capability),
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            dependency_setup=dependency_setup,
        )
        | _timeout_output_diagnostics(stdout=stdout, stderr=stderr)
        | _read_only_mutation_diagnostics(mutation)
    )
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
        **_optional_field("artifact_digest", artifact_digest(stdout, stderr)),
        "failure_type": gate_failure_type,
        "reason": "gate timed out",
        "diagnostics": diagnostics,
        **recommended_action(
            environment_restricted=environment_restricted,
            dependency_setup=dependency_setup,
        ),
        **dependency_setup_action(diagnostics),
        **_optional_field("recommended_action", _read_only_mutation_action(mutation)),
    }


def _completed_result(
    *,
    repo_root: Path,
    capability: dict[str, Any],
    capability_id: str,
    capability_kind: str,
    command: str,
    source: str | None,
    risk: str,
    timeout_seconds: int,
    started: float,
    readonly_snapshot: TrackedSnapshot | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    stdout = _truncate(result["stdout"])
    stderr = _truncate(result["stderr"])
    gate_failure_type = failure_type(command=command, stdout=stdout, stderr=stderr, timed_out=False)
    returncode = result["returncode"] if isinstance(result["returncode"], int) else 1
    mutation = restore_if_changed(repo_root, readonly_snapshot)
    if mutation is not None:
        gate_failure_type = "read-only-mutation"
    failed = returncode != 0 or mutation is not None
    environment_restricted = failed and gate_failure_type == "environment-restricted"
    dependency_setup = failed and gate_failure_type == "dependency-setup-blocker"
    diagnostics = (
        gate_diagnostics(
            command=command,
            cwd=gate_cwd(repo_root=repo_root, capability=capability),
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
            dependency_setup=dependency_setup,
        )
        | _read_only_mutation_diagnostics(mutation)
        if dependency_setup or mutation is not None
        else None
    )
    return {
        "id": capability_id,
        "status": "failed" if failed else "passed",
        "capability_kind": capability_kind,
        "command": command,
        "source": source,
        "exit_code": returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timeout_seconds": timeout_seconds,
        "cwd": str(gate_cwd(repo_root=repo_root, capability=capability)),
        "mutating_risk": risk,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        **_optional_field("artifact_digest", artifact_digest(stdout, stderr)),
        **_optional_field("failure_type", gate_failure_type if failed else None),
        **_optional_field("diagnostics", diagnostics),
        **recommended_action(
            environment_restricted=environment_restricted,
            dependency_setup=dependency_setup,
        ),
        **dependency_setup_action(diagnostics),
        **_optional_field("recommended_action", _read_only_mutation_action(mutation)),
    }


def _capability_kind(capability: dict[str, Any]) -> str:
    kind = capability.get("capability_kind")
    if kind in {"local_command", "ci_only", "evidence_file", "agent_review", "evidence"}:
        return str(kind)
    if capability.get("local_execution") == "ci-only":
        return "ci_only"
    if capability.get("type") == "file":
        return "evidence_file"
    return "local_command"


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _truncate(value: object) -> str:
    text = value if isinstance(value, str) else ""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + "\n[truncated]\n"


def _optional_field(key: str, value: object) -> dict[str, Any]:
    return {} if value is None else {key: value}


def _read_only_mutation_diagnostics(mutation: dict[str, Any] | None) -> dict[str, Any]:
    return {} if mutation is None else {"read_only_mutation": mutation}


def _read_only_mutation_action(mutation: dict[str, Any] | None) -> str | None:
    if mutation is None:
        return None
    if mutation.get("restored") is True:
        return (
            "gate mutated tracked files during read-only verification; QR restored the pre-gate "
            "tracked diff, rerun directly only when source changes are allowed"
        )
    return (
        "gate mutated tracked files during read-only verification and QR could not fully restore "
        "them; inspect the tracked diff before continuing"
    )


def _timeout_output_diagnostics(*, stdout: str, stderr: str) -> dict[str, Any]:
    status = "captured-partial-output" if stdout or stderr else "timeout-with-no-output"
    return {"timeout_output_status": status}
