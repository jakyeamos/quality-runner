from __future__ import annotations

import fnmatch
import hashlib
import json
import subprocess
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from quality_runner import __version__
from quality_runner.edge_trace import read_trace, receipt_trace, store_private_trace, validate_trace
from quality_runner.fleet.behavior_contract import (
    CONTRACT_PATH,
    CONTRACT_SCHEMA,
    CONTRACT_SCHEMAS,
    EDGE_ENVIRONMENTS,
    EDGE_SURFACES,
    RECEIPT_DIRECTORY,
    RECEIPT_SCHEMA,
)
from quality_runner.fleet.contracts import digest

MAX_COMMAND_OUTPUT_BYTES = 64_000


def verify_behavior_command(
    *,
    repo_root: Path,
    behavior_id: str,
    scenario_ids: Sequence[str],
    command: Sequence[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    """Run one bounded validator and seal its result as an immutable receipt."""

    root = repo_root.expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    argv = [item for item in command if item]
    if argv[:1] == ["--"]:
        argv = argv[1:]
    if not argv:
        raise ValueError("behavior verify requires a validator command after --")

    contract_path = root / CONTRACT_PATH
    contract = _read_json_object(contract_path)
    if (
        contract.get("schema") not in CONTRACT_SCHEMAS
        or contract.get("applicability") != "applicable"
    ):
        raise ValueError("behavior verify requires a compatible applicable behavior contract")
    approved = [
        item
        for item in _object_list(contract.get("approved_producers", ["quality-runner"]))
        if isinstance(item, str)
    ]
    if "quality-runner" not in approved:
        raise ValueError("the behavior contract does not approve the quality-runner producer")
    _require_committed_contract(root)

    behavior = next(
        (
            item
            for item in _object_mappings(contract.get("behaviors", []))
            if item.get("id") == behavior_id
        ),
        None,
    )
    if behavior is None:
        raise ValueError(f"unknown behavior id: {behavior_id}")
    scenarios = _object_mappings(behavior.get("scenarios", []))
    selected_ids = list(dict.fromkeys(scenario_ids)) or [
        str(item.get("id", "")) for item in scenarios
    ]
    selected = [item for item in scenarios if item.get("id") in selected_ids]
    missing = sorted(set(selected_ids) - {str(item.get("id")) for item in selected})
    if missing:
        raise ValueError(f"unknown scenario ids for {behavior_id}: {', '.join(missing)}")
    if not selected:
        raise ValueError(f"behavior {behavior_id} has no scenarios to verify")
    unsupported = [
        str(item.get("id"))
        for item in selected
        if item.get("verification_level") not in {"source", "automated"}
    ]
    if unsupported:
        raise ValueError(
            "command receipts cannot satisfy direct_surface or independent scenarios: "
            + ", ".join(unsupported)
        )

    branch = _git_one(root, "branch", "--show-current")
    commit = _git_one(root, "rev-parse", "HEAD")
    if not branch or not commit:
        raise ValueError("behavior verify requires a named Git branch and target commit")
    dirty_paths = _dirty_paths(root)
    triggers = [
        item for item in _object_list(behavior.get("change_triggers", [])) if isinstance(item, str)
    ]
    relevant_dirty = sorted(
        path for path in dirty_paths if any(fnmatch.fnmatch(path, pattern) for pattern in triggers)
    )
    if relevant_dirty:
        raise ValueError(
            "commit the behavior's changed trigger paths before validation: "
            + ", ".join(relevant_dirty)
        )

    started = time.monotonic()
    status = "passed"
    exit_code: int | None = None
    stdout = b""
    stderr = b""
    try:
        completed = subprocess.run(
            argv,
            cwd=root,
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
        )
        exit_code = completed.returncode
        stdout = completed.stdout[-MAX_COMMAND_OUTPUT_BYTES:]
        stderr = completed.stderr[-MAX_COMMAND_OUTPUT_BYTES:]
        status = "passed" if completed.returncode == 0 else "failed"
    except subprocess.TimeoutExpired as error:
        status = "blocked"
        stdout = (error.stdout or b"")[-MAX_COMMAND_OUTPUT_BYTES:]
        stderr = (error.stderr or b"")[-MAX_COMMAND_OUTPUT_BYTES:]
    except OSError as error:
        status = "blocked"
        stderr = str(error).encode("utf-8")[-MAX_COMMAND_OUTPUT_BYTES:]
    duration_ms = round((time.monotonic() - started) * 1000)
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    evidence = {
        "kind": "bounded_command",
        "argv": argv,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "timeout_seconds": timeout_seconds,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_truncated": len(stdout) == MAX_COMMAND_OUTPUT_BYTES,
        "stderr_truncated": len(stderr) == MAX_COMMAND_OUTPUT_BYTES,
    }
    unsigned: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "contract_digest": digest(contract),
        "producer": {"id": "quality-runner", "version": __version__},
        "target": {"branch": branch, "commit": commit},
        "generated_at": generated_at,
        "results": [
            {
                "behavior_id": behavior_id,
                "scenario_id": str(scenario["id"]),
                "status": status,
                "verification_level": "automated",
                "evidence": [evidence],
            }
            for scenario in selected
        ],
    }
    receipt_id = f"receipt-{digest(unsigned)[:24]}"
    receipt = {"receipt_id": receipt_id, **unsigned}
    directory = root / RECEIPT_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"{receipt_id}.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    return {
        "schema": "quality-runner-behavior-verification/v1",
        "status": status,
        "receipt_id": receipt_id,
        "receipt_path": output.relative_to(root).as_posix(),
        "behavior_id": behavior_id,
        "scenario_ids": [str(item["id"]) for item in selected],
        "target_branch": branch,
        "target_commit": commit,
        "command": argv,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
    }


def record_edge_trace(
    *,
    repo_root: Path,
    behavior_id: str,
    scenario_id: str,
    environment: str,
    surface: str,
    status: str,
    trace_path: Path,
) -> dict[str, Any]:
    """Validate a hostile-session trace and seal direct-surface evidence."""

    root = repo_root.expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    if environment not in EDGE_ENVIRONMENTS:
        raise ValueError("edge evidence is allowed only for local, test, preview, or staging")
    if surface not in EDGE_SURFACES:
        raise ValueError(f"unsupported edge surface: {surface}")
    if status not in {"passed", "failed", "blocked"}:
        raise ValueError("edge status must be passed, failed, or blocked")

    contract = _read_json_object(root / CONTRACT_PATH)
    if contract.get("schema") != CONTRACT_SCHEMA or contract.get("applicability") != "applicable":
        raise ValueError("behavior record-edge requires an applicable v2 behavior contract")
    approved = [
        item
        for item in _object_list(contract.get("approved_producers", ["quality-runner"]))
        if isinstance(item, str)
    ]
    if "quality-runner" not in approved:
        raise ValueError("the behavior contract does not approve the quality-runner producer")
    _require_committed_contract(root)
    behavior, scenario = _select_scenario(contract, behavior_id, scenario_id)
    if scenario.get("verification_level") == "independent":
        raise ValueError("record-edge cannot satisfy independent verification")
    profile = scenario.get("edge_profile")
    if not isinstance(profile, dict):
        raise ValueError("record-edge requires a scenario edge_profile")
    profile = cast(dict[str, Any], profile)
    if profile.get("side_effects") == "destructive":
        raise ValueError("destructive edge scenarios require a separately authorized producer")
    _require_clean_triggers(root, behavior)

    trace = read_trace(trace_path)
    validate_trace(
        trace,
        behavior=behavior,
        scenario=scenario,
        environment=environment,
        surface=surface,
        status=status,
    )
    trace_sha256 = digest(trace)
    private_trace_id: str | None = None
    if trace["sensitivity"] == "security_sensitive":
        private_trace_id = store_private_trace(trace, trace_sha256)
    evidence_trace = receipt_trace(
        trace,
        trace_sha256=trace_sha256,
        environment=environment,
        surface=surface,
    )

    branch = _git_one(root, "branch", "--show-current")
    commit = _git_one(root, "rev-parse", "HEAD")
    if not branch or not commit:
        raise ValueError("behavior record-edge requires a named Git branch and target commit")
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    unsigned: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "contract_digest": digest(contract),
        "producer": {"id": "quality-runner", "version": __version__},
        "target": {"branch": branch, "commit": commit},
        "generated_at": generated_at,
        "results": [
            {
                "behavior_id": behavior_id,
                "scenario_id": scenario_id,
                "status": status,
                "verification_level": "direct_surface",
                "evidence": [
                    {
                        "kind": "direct_surface",
                        "surface": surface,
                        "environment": environment,
                        "observation": str(trace["observation"])[:2_000],
                    },
                    evidence_trace,
                ],
            }
        ],
    }
    receipt_id = f"receipt-{digest(unsigned)[:24]}"
    receipt = {"receipt_id": receipt_id, **unsigned}
    output = _write_receipt(root, receipt_id, receipt)
    return {
        "schema": "quality-runner-edge-recording/v1",
        "status": status,
        "receipt_id": receipt_id,
        "receipt_path": output.relative_to(root).as_posix(),
        "behavior_id": behavior_id,
        "scenario_id": scenario_id,
        "target_branch": branch,
        "target_commit": commit,
        "environment": environment,
        "surface": surface,
        "trace_sha256": trace_sha256,
        "sensitivity": trace["sensitivity"],
        "private_trace_id": private_trace_id,
    }


def _select_scenario(
    contract: dict[str, Any], behavior_id: str, scenario_id: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    behavior = next(
        (
            item
            for item in _object_mappings(contract.get("behaviors", []))
            if item.get("id") == behavior_id
        ),
        None,
    )
    if behavior is None:
        raise ValueError(f"unknown behavior id: {behavior_id}")
    scenario = next(
        (
            item
            for item in _object_mappings(behavior.get("scenarios", []))
            if item.get("id") == scenario_id
        ),
        None,
    )
    if scenario is None:
        raise ValueError(f"unknown scenario id for {behavior_id}: {scenario_id}")
    return behavior, scenario


def _require_clean_triggers(root: Path, behavior: dict[str, Any]) -> None:
    triggers = [
        item for item in _object_list(behavior.get("change_triggers", [])) if isinstance(item, str)
    ]
    relevant = sorted(
        path
        for path in _dirty_paths(root)
        if any(fnmatch.fnmatch(path, pattern) for pattern in triggers)
    )
    if relevant:
        raise ValueError(
            "commit the behavior's changed trigger paths before recording edge evidence: "
            + ", ".join(relevant)
        )


def _write_receipt(root: Path, receipt_id: str, receipt: dict[str, Any]) -> Path:
    directory = root / RECEIPT_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"{receipt_id}.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    return output


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read behavior contract: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("behavior contract JSON root must be an object")
    return cast(dict[str, Any], value)


def _object_list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _object_mappings(value: object) -> list[dict[str, Any]]:
    return [cast(dict[str, Any], item) for item in _object_list(value) if isinstance(item, dict)]


def _require_committed_contract(root: Path) -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", CONTRACT_PATH.as_posix()],
        cwd=root,
        check=False,
        capture_output=True,
        timeout=10,
    )
    unchanged = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", CONTRACT_PATH.as_posix()],
        cwd=root,
        check=False,
        capture_output=True,
        timeout=10,
    )
    if tracked.returncode != 0 or unchanged.returncode != 0:
        raise ValueError("commit .pronto/behavior-assurance.json before producing receipts")


def _dirty_paths(root: Path) -> list[str]:
    lines = _git_lines(root, "status", "--porcelain=v1", "--untracked-files=all")
    return [path for line in lines if (path := _porcelain_path(line))]


def _git_one(root: Path, *args: str) -> str | None:
    return next(iter(_git_lines(root, *args)), None)


def _git_lines(root: Path, *args: str) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return completed.stdout.splitlines() if completed.returncode == 0 else []


def _porcelain_path(line: str) -> str:
    value = line[3:].strip() if len(line) > 3 else ""
    return value.split(" -> ", maxsplit=1)[-1]
