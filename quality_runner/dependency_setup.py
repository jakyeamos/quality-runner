from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.gate_execution_policy import (
    gate_cwd,
    mutating_risk,
    package_manager_for_command,
    recommended_action,
    timeout_diagnostics,
)


def dependency_setup_context(*, repo_root: Path, capability: dict[str, Any]) -> tuple[str, str]:
    command = capability.get("command")
    command_text = command if isinstance(command, str) else ""
    return (
        package_manager_for_command(command_text) or "",
        str(gate_cwd(repo_root=repo_root, capability=capability)),
    )


def dependency_setup_skipped_gate(
    *,
    repo_root: Path,
    capability: dict[str, Any],
    timeout_seconds: int,
    blocked_by: dict[str, Any],
) -> dict[str, Any]:
    command = capability.get("command")
    command_text = command if isinstance(command, str) else ""
    cwd = gate_cwd(repo_root=repo_root, capability=capability)
    capability_id = str(capability.get("id") or "unknown")
    dependency_setup = _dependency_setup_diagnostics_from(blocked_by)
    if dependency_setup is None:
        dependency_setup = dependency_setup_diagnostics(command=command_text, cwd=cwd)
    return {
        "id": capability_id,
        "status": "skipped",
        "capability_kind": _capability_kind(capability),
        "command": command_text,
        "source": _string_or_none(capability.get("source")),
        "cwd": str(cwd),
        "mutating_risk": mutating_risk(capability_id=capability_id, capability=capability),
        "timeout_seconds": timeout_seconds,
        "failure_type": "dependency-setup-blocker",
        "skip_type": "dependency-setup-blocked",
        "reason": "skipped because an earlier gate hit the same dependency setup blocker",
        "blocked_by": str(blocked_by.get("id") or "unknown"),
        "diagnostics": {"dependency_setup": dependency_setup},
        **recommended_action(environment_restricted=False, dependency_setup=True),
    }


def gate_diagnostics(
    *,
    command: str,
    cwd: Path,
    stdout: str,
    stderr: str,
    timed_out: bool,
    dependency_setup: bool,
) -> dict[str, Any]:
    diagnostics = (
        timeout_diagnostics(command=command, stdout=stdout, stderr=stderr)
        if timed_out
        else {}
    )
    if dependency_setup:
        diagnostics["dependency_setup"] = dependency_setup_diagnostics(
            command=command,
            cwd=cwd,
            stdout=stdout,
            stderr=stderr,
        )
    return diagnostics


def dependency_setup_diagnostics(
    *,
    command: str,
    cwd: Path,
    stdout: str = "",
    stderr: str = "",
) -> dict[str, str | None]:
    package_manager = package_manager_for_command(command)
    ignored_builds = _pnpm_ignored_builds(stdout=stdout, stderr=stderr)
    return {
        "package_manager": package_manager,
        "cwd": str(cwd),
        "setup_command": _setup_command(package_manager, ignored_builds=ignored_builds),
        "cause": _cause(ignored_builds=ignored_builds),
    }


def _setup_command(package_manager: str | None, *, ignored_builds: bool) -> str | None:
    if package_manager == "pnpm" and ignored_builds:
        return "pnpm approve-builds"
    if package_manager == "pnpm":
        return "pnpm install --frozen-lockfile"
    if package_manager == "npm":
        return "npm ci"
    if package_manager == "yarn":
        return "yarn install --immutable"
    if package_manager == "bun":
        return "bun install --frozen-lockfile"
    return None


def _cause(*, ignored_builds: bool) -> str:
    if ignored_builds:
        return "package manager blocked dependency build scripts until approved"
    return "package manager attempted dependency restoration in a non-interactive gate run"


def _pnpm_ignored_builds(*, stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}".lower()
    return (
        "err_pnpm_ignored_builds" in combined
        or "ignored build scripts" in combined
        or "pnpm approve-builds" in combined
    )


def _dependency_setup_diagnostics_from(gate: dict[str, Any]) -> dict[str, str | None] | None:
    diagnostics = gate.get("diagnostics")
    if not isinstance(diagnostics, dict):
        return None
    dependency_setup = diagnostics.get("dependency_setup")
    if not isinstance(dependency_setup, dict):
        return None
    return {
        "package_manager": _string_or_none(dependency_setup.get("package_manager")),
        "cwd": _string_or_none(dependency_setup.get("cwd")),
        "setup_command": _string_or_none(dependency_setup.get("setup_command")),
        "cause": _string_or_none(dependency_setup.get("cause")),
    }


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
