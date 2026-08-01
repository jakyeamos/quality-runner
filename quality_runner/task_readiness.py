from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.schema_constants import PREVENTION_READINESS_SCHEMA

REQUIRED_CERTIFICATION_EVIDENCE = {"failure-fixture", "repeat-pass", "local", "ci"}
SAFE_MUTATION_RISKS = {"read-only", "isolated-only"}
UNSAFE_COMMAND_TOKENS = {"&&", "||", ";", "|", ">", ">>", "<"}
BLOCKED_OUTPUT_MARKERS = {
    "command not found",
    "failed to initialize cache",
    "no such file or directory",
    "operation not permitted",
    "permission denied",
}
MINIMUM_BOOTSTRAP_TIMEOUT_SECONDS = 15


def evaluate_readiness(
    *,
    repo_root: Path,
    prevention: dict[str, Any],
) -> dict[str, Any]:
    global_environment_paths = prevention.get("environment_paths", [])
    gates: list[dict[str, Any]] = []
    for configured in prevention.get("gates", []):
        if not isinstance(configured, dict):
            continue
        gates.append(
            _evaluate_gate(
                repo_root=repo_root,
                configured=configured,
                global_environment_paths=global_environment_paths,
            )
        )
    toolchain = [
        {
            "id": item["id"],
            "command_path": item.get("command_path"),
            "command_version": item.get("command_version"),
            "state": item["state"],
        }
        for item in gates
    ]
    return {
        "schema": PREVENTION_READINESS_SCHEMA,
        "gates": gates,
        "summary": {
            state: sum(item["state"] == state for item in gates)
            for state in ("candidate", "certified", "blocked", "unavailable")
        },
        "toolchain_hash": _hash_payload(toolchain),
    }


def run_certified_gates(
    *,
    snapshot_root: Path,
    repo_root: Path,
    readiness: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    results: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    bootstrap_results: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    for gate in readiness.get("gates", []):
        if not isinstance(gate, dict):
            continue
        if gate.get("state") != "certified":
            if gate.get("required") is True:
                blockers.append(
                    {
                        "code": "required_gate_not_certified",
                        "message": f"required gate {gate.get('id')} is {gate.get('state')}",
                    }
                )
            continue
        environment_paths = [
            Path(path)
            for path in gate.get("resolved_environment_paths", [])
            if isinstance(path, str)
        ]
        bootstrap_key = (
            str(gate.get("bootstrap") or ""),
            tuple(str(path) for path in environment_paths),
        )
        bootstrap = bootstrap_results.get(bootstrap_key)
        if bootstrap is None:
            bootstrap = _run_bootstrap(
                snapshot_root=snapshot_root,
                gate=gate,
                environment_paths=environment_paths,
            )
            bootstrap_results[bootstrap_key] = bootstrap
        if bootstrap["status"] != "passed":
            result = _gate_result(
                gate,
                status="blocked",
                exit_code=bootstrap.get("exit_code"),
                stdout="",
                stderr=f"certified gate bootstrap failed: {bootstrap.get('stderr', '')}",
                bootstrap=bootstrap,
            )
            results.append(result)
            blockers.append(
                {
                    "code": "gate_evidence_unknown",
                    "message": f"gate {gate.get('id')} bootstrap is {bootstrap['status']}",
                }
            )
            continue
        result = _run_gate(
            snapshot_root=snapshot_root,
            repo_root=repo_root,
            gate=gate,
            bootstrap=bootstrap,
        )
        results.append(result)
        if result["status"] in {"timeout", "unavailable", "blocked"}:
            blockers.append(
                {
                    "code": "gate_evidence_unknown",
                    "message": f"gate {gate.get('id')} is {result['status']}",
                }
            )
    return results, blockers


def _run_bootstrap(
    *,
    snapshot_root: Path,
    gate: dict[str, Any],
    environment_paths: list[Path],
) -> dict[str, Any]:
    command = str(gate.get("bootstrap") or "")
    try:
        argv = _command_argv(command)
    except ValueError as error:
        return {
            "command": command,
            "status": "blocked",
            "exit_code": None,
            "stdout": "",
            "stderr": str(error),
        }
    command_path = shutil.which(argv[0], path=_search_path(environment_paths))
    if command_path is None:
        return {
            "command": command,
            "command_path": None,
            "status": "unavailable",
            "exit_code": None,
            "stdout": "",
            "stderr": f"bootstrap command not found: {argv[0]}",
        }
    argv[0] = command_path
    environment = _gate_environment(snapshot_root, environment_paths)
    command_version = _command_version(
        Path(command_path),
        snapshot_root,
        environment_paths,
        environment=environment,
    )
    if command_version is None:
        return {
            "command": command,
            "command_path": command_path,
            "command_version": None,
            "status": "blocked",
            "exit_code": None,
            "stdout": "",
            "stderr": "bootstrap command did not provide verifiable version output",
        }
    # The gate timeout measures the check itself. A deliberately short gate
    # timeout (for example, a timeout-behaviour fixture) must not accidentally
    # turn ordinary interpreter/bootstrap startup into the evidence result.
    timeout = min(
        max(
            int(gate.get("timeout_seconds") or 120),
            MINIMUM_BOOTSTRAP_TIMEOUT_SECONDS,
        ),
        300,
    )
    try:
        result = subprocess.run(
            argv,
            cwd=snapshot_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "command": command,
            "command_path": command_path,
            "command_version": command_version,
            "status": "timeout",
            "exit_code": None,
            "stdout": _bounded_output(error.stdout),
            "stderr": _bounded_output(error.stderr),
        }
    except OSError as error:
        return {
            "command": command,
            "command_path": command_path,
            "command_version": command_version,
            "status": "unavailable",
            "exit_code": None,
            "stdout": "",
            "stderr": str(error),
        }
    return {
        "command": command,
        "command_path": command_path,
        "command_version": command_version,
        "status": "passed" if result.returncode == 0 else "blocked",
        "exit_code": result.returncode,
        "stdout": _bounded_output(result.stdout),
        "stderr": _bounded_output(result.stderr),
    }


def required_gate_failures(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item for item in results if item.get("required") is True and item.get("status") == "failed"
    ]


def _evaluate_gate(
    *,
    repo_root: Path,
    configured: dict[str, Any],
    global_environment_paths: object,
) -> dict[str, Any]:
    gate = dict(configured)
    environment_paths = _environment_paths(
        repo_root,
        [
            *(global_environment_paths if isinstance(global_environment_paths, list) else []),
            *(
                configured["environment_paths"]
                if isinstance(configured.get("environment_paths"), list)
                else []
            ),
        ],
    )
    gate["resolved_environment_paths"] = [str(path) for path in environment_paths]
    try:
        argv = _command_argv(str(configured.get("command") or ""))
    except ValueError as error:
        return {**gate, "state": "blocked", "blocker": str(error)}
    command_path = shutil.which(argv[0], path=_search_path(environment_paths))
    if command_path is None:
        return {
            **gate,
            "state": "unavailable",
            "command_path": None,
            "command_version": None,
            "blocker": f"command not found: {argv[0]}",
        }
    version = _command_version(Path(command_path), repo_root, environment_paths)
    gate["command_path"] = command_path
    gate["command_version"] = version
    gate["argv"] = argv
    configured_state = configured.get("state")
    if configured_state in {"blocked", "unavailable"}:
        gate["state"] = configured_state
        gate["blocker"] = configured.get("blocker") or f"gate declared {configured_state}"
        return gate
    if configured_state != "certified":
        gate["state"] = "candidate"
        return gate
    issues = _certification_issues(configured)
    if version is None:
        issues.append("resolved command did not provide verifiable version output")
    if issues:
        gate["state"] = "blocked"
        gate["blocker"] = "; ".join(issues)
        return gate
    gate["state"] = "certified"
    return gate


def _certification_issues(configured: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    evidence = {
        item.split(":", 1)[0]
        for item in configured.get("evidence_refs", [])
        if isinstance(item, str) and ":" in item
    }
    missing = sorted(REQUIRED_CERTIFICATION_EVIDENCE - evidence)
    if missing:
        issues.append(f"missing certification evidence: {', '.join(missing)}")
    for field in ("owner", "rationale", "bootstrap", "scope"):
        if not configured.get(field):
            issues.append(f"missing {field}")
    if configured.get("mutation_risk") not in SAFE_MUTATION_RISKS:
        issues.append("mutation_risk must be read-only or isolated-only")
    return issues


def _run_gate(
    *,
    snapshot_root: Path,
    repo_root: Path,
    gate: dict[str, Any],
    bootstrap: dict[str, Any],
) -> dict[str, Any]:
    argv = list(gate.get("argv", []))
    snapshot_command = snapshot_root / ".venv" / "bin" / Path(argv[0]).name
    argv[0] = str(snapshot_command) if snapshot_command.is_file() else str(gate["command_path"])
    executed_command_path = argv[0]
    environment_paths = [
        Path(path) for path in gate.get("resolved_environment_paths", []) if isinstance(path, str)
    ]
    environment = _gate_environment(snapshot_root, environment_paths)
    timeout = int(gate.get("timeout_seconds") or 120)
    try:
        result = subprocess.run(
            argv,
            cwd=snapshot_root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return _gate_result(
            gate,
            status="timeout",
            exit_code=None,
            stdout=_bounded_output(error.stdout),
            stderr=_bounded_output(error.stderr),
            bootstrap=bootstrap,
            executed_command_path=executed_command_path,
        )
    except OSError as error:
        return _gate_result(
            gate,
            status="unavailable",
            exit_code=None,
            stdout="",
            stderr=str(error),
            bootstrap=bootstrap,
            executed_command_path=executed_command_path,
        )
    output = f"{result.stdout}\n{result.stderr}".lower()
    status = (
        "passed"
        if result.returncode == 0
        else "blocked"
        if any(marker in output for marker in BLOCKED_OUTPUT_MARKERS)
        else "failed"
    )
    return _gate_result(
        gate,
        status=status,
        exit_code=result.returncode,
        stdout=_bounded_output(result.stdout),
        stderr=_bounded_output(result.stderr),
        bootstrap=bootstrap,
        executed_command_path=executed_command_path,
    )


def _gate_result(
    gate: dict[str, Any],
    *,
    status: str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    bootstrap: dict[str, Any] | None = None,
    executed_command_path: str | None = None,
) -> dict[str, Any]:
    return {
        "id": gate.get("id"),
        "required": gate.get("required") is True,
        "status": status,
        "exit_code": exit_code,
        "command": gate.get("command"),
        "command_path": gate.get("command_path"),
        "executed_command_path": executed_command_path or gate.get("command_path"),
        "command_version": gate.get("command_version"),
        "timeout_seconds": gate.get("timeout_seconds"),
        "stdout": stdout,
        "stderr": stderr,
        "bootstrap": bootstrap,
    }


def _command_argv(command: str) -> list[str]:
    try:
        argv = shlex.split(command)
    except ValueError as error:
        raise ValueError(f"invalid gate command: {error}") from error
    if not argv:
        raise ValueError("gate command must not be empty")
    if any(token in UNSAFE_COMMAND_TOKENS for token in argv):
        raise ValueError("gate commands must be direct argv commands without shell operators")
    return argv


def _environment_paths(repo_root: Path, values: list[object]) -> list[Path]:
    result: list[Path] = []
    for item in values:
        if not isinstance(item, str) or not item:
            continue
        path = (repo_root / item).resolve()
        try:
            path.relative_to(repo_root)
        except ValueError:
            continue
        if path.is_dir() and path not in result:
            result.append(path)
    return result


def _search_path(environment_paths: list[Path]) -> str:
    existing = os.environ.get("PATH", "")
    return os.pathsep.join([*(str(path) for path in environment_paths), existing])


def _command_version(
    command_path: Path,
    repo_root: Path,
    environment_paths: list[Path],
    *,
    environment: dict[str, str] | None = None,
) -> str | None:
    command_environment = (
        environment
        if environment is not None
        else {**os.environ, "PATH": _search_path(environment_paths)}
    )
    try:
        result = subprocess.run(
            [str(command_path), "--version"],
            cwd=repo_root,
            env=command_environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (result.stdout or result.stderr).strip()
    return text.splitlines()[0][:300] if result.returncode == 0 and text else None


def _gate_environment(snapshot_root: Path, environment_paths: list[Path]) -> dict[str, str]:
    cache_root = snapshot_root / ".quality-runner-gate-cache"
    cache_root.mkdir(exist_ok=True)
    environment = dict(os.environ)
    for variable in ("PYTHONPATH", "UV_PYTHON", "UV_PROJECT_ENVIRONMENT", "VIRTUAL_ENV"):
        environment.pop(variable, None)
    environment.update(
        {
            "PATH": _search_path(environment_paths),
            "PYTHONPYCACHEPREFIX": str(cache_root / "pycache"),
            "XDG_CACHE_HOME": str(cache_root / "xdg"),
            "XDG_CONFIG_HOME": str(cache_root / "xdg-config"),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "CI": "1",
        }
    )
    return environment


def _bounded_output(value: object, limit: int = 20_000) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = value if isinstance(value, str) else ""
    return text[-limit:]


def _hash_payload(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
