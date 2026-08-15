from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from quality_runner.artifacts import prepare_safe_directory
from quality_runner.fleet.contracts import digest, hash_text, redact_text
from quality_runner.fleet.dependencies import (
    prepare_dynamic_dependencies as _prepare_dependency_tree,
)
from quality_runner.fleet.dependencies import (
    remove_runtime_path,
)
from quality_runner.fleet.dependency_sources import (
    compatible_dependency_source as _dependency_source,
)
from quality_runner.fleet.dependency_sources import (
    compatible_local_dependency_source as _local_dependency_source,
)
from quality_runner.fleet.discovery import checkout_fingerprint
from quality_runner.fleet.dynamic_commands import (
    aggregate_dynamic_status as _aggregate_dynamic_status,
)
from quality_runner.fleet.dynamic_commands import command_timeout as _command_timeout
from quality_runner.fleet.dynamic_commands import (
    configured_gate_timeouts as _configured_gate_timeouts,
)
from quality_runner.fleet.dynamic_commands import (
    dynamic_policy_block_reason as _dynamic_policy_block_reason,
)
from quality_runner.fleet.dynamic_commands import run_dynamic_command
from quality_runner.fleet.dynamic_commands import safe_dynamic_command as _safe_dynamic_command
from quality_runner.fleet.dynamic_findings import apply_dynamic_quality_evidence
from quality_runner.fleet.dynamic_scan import quality_commands_from_worktree
from quality_runner.fleet.repository_lifecycle import (
    documented_archival_repository as _documented_archival_repository,
)
from quality_runner.fleet.repository_lifecycle import (
    documented_deprecated_repository as _documented_deprecated_repository,
)
from quality_runner.process_runner import run_command, run_shell_command

__all__ = ["apply_dynamic_quality_evidence", "dynamic_result"]


def _prepare_dynamic_dependencies(
    *,
    worktree: Path,
    source: Path | None = None,
    local_source: Path | None = None,
    timeout_seconds: int,
) -> dict[str, Any]:
    return _prepare_dependency_tree(
        worktree=worktree,
        source=source,
        local_source=local_source,
        timeout_seconds=timeout_seconds,
        run_command=run_shell_command,
    )


def dynamic_result(
    *,
    repository: dict[str, Any],
    finding: dict[str, Any],
    audit_id: str,
    artifact_root: Path,
    enabled: bool,
    changed_only: bool,
    max_age_days: int,
    timeout_seconds: int,
    as_of: str,
) -> dict[str, Any]:
    if not enabled:
        return {
            "status": "not_selected",
            "selected": False,
            "reason": "dynamic verification was not requested",
        }
    target = repository.get("target_branch")
    if not isinstance(target, dict):
        return {"status": "blocked", "selected": True, "reason": "target branch is unresolved"}
    target = cast(dict[str, Any], target)
    target_state = target.get("target_state")
    target_head = target.get("head")
    signature = digest(
        {
            "repo": repository.get("repo_id"),
            "head": target_head,
            "quality_commands": cast(dict[str, Any], finding.get("scan", {})).get(
                "quality_commands", []
            ),
        }
    )
    previous = _find_previous_dynamic(
        artifact_root=artifact_root,
        repo_id=str(repository["repo_id"]),
        target_head=target_head,
        signature=signature,
        as_of=as_of,
        max_age_days=max_age_days,
    )
    if previous is not None:
        return {
            **previous,
            "status": "reused",
            "selected": False,
            "reason": "passing dynamic evidence is within its configured expiry",
        }
    reasons = [
        "no prior passing dynamic evidence",
        *_selection_reasons(repository=repository, finding=finding, target_head=target_head),
    ]
    if changed_only and not reasons:
        return {
            "status": "not_selected",
            "selected": False,
            "reason": "no changed-only trigger was found",
            "signature": signature,
        }
    if (
        not isinstance(target_state, dict)
        or cast(dict[str, Any], target_state).get("status") != "ready"
    ):
        return {
            "status": "blocked",
            "selected": True,
            "selection_reasons": reasons or ["priority or incomplete evidence"],
            "reason": target.get("reason", "target branch is not ready"),
            "target_branch": target.get("branch"),
            "target_head": target_head,
            "target_state": target_state,
            "signature": signature,
        }
    source_checkout_id = target.get("checkout_id")
    source_checkout = next(
        (
            item
            for item in cast(list[dict[str, Any]], repository.get("checkouts", []))
            if item.get("checkout_id") == source_checkout_id
        ),
        None,
    )
    if not isinstance(source_checkout, dict):
        return {
            "status": "blocked",
            "selected": True,
            "reason": "target checkout record is missing",
            "signature": signature,
        }
    return _execute_dynamic(
        repository={**repository, "scan": finding.get("scan", {})},
        source_checkout=source_checkout,
        target=target,
        reasons=reasons or ["priority or incomplete evidence"],
        artifact_root=artifact_root,
        timeout_seconds=timeout_seconds,
        signature=signature,
        audit_id=audit_id,
    )


def _execute_dynamic(
    *,
    repository: dict[str, Any],
    source_checkout: dict[str, Any],
    target: dict[str, Any],
    reasons: list[str],
    artifact_root: Path,
    timeout_seconds: int,
    signature: str,
    audit_id: str,
) -> dict[str, Any]:
    del audit_id
    source = Path(str(source_checkout["path"])).expanduser().resolve()
    head = str(target.get("head"))
    result: dict[str, Any] = {
        "status": "unknown",
        "selected": True,
        "selection_reasons": reasons,
        "target_branch": target.get("branch"),
        "target_head": head,
        "source_checkout_id": source_checkout.get("checkout_id"),
        "signature": signature,
        "commands": [],
        "implementation_allowed": False,
    }
    worktree = artifact_root / "worktrees" / str(repository["repo_id"])
    prepare_safe_directory(worktree.parent)
    before = checkout_fingerprint(source)
    if worktree.exists() or worktree.is_symlink():
        result["status"] = "blocked"
        result["reason"] = "runtime-owned disposable worktree path already exists"
        result["source_integrity_before"] = before
        return result
    setup = _git_command(source, "worktree", "add", "--detach", str(worktree), head, timeout=30)
    if setup["returncode"] != 0 or not worktree.is_dir():
        cleanup = _git_command(source, "worktree", "remove", "--force", str(worktree), timeout=30)
        result["status"] = "blocked"
        result["reason"] = (
            redact_text(setup["stderr"] or setup["stdout"], root=source)[:500]
            if setup["returncode"] != 0
            else "git worktree add reported success but the disposable directory is unavailable"
        )
        result["cleanup"] = {
            "status": "passed" if cleanup["returncode"] == 0 else "failed",
            "returncode": cleanup["returncode"],
        }
        result["source_integrity_before"] = before
        after = checkout_fingerprint(source)
        result["source_integrity_after"] = after
        result["source_unchanged"] = before == after
        return result
    dependency_cleanup_paths: list[Path] = []
    try:
        statuses: list[str] = []
        if _documented_deprecated_repository(worktree):
            result["status"] = "not_applicable"
            result["reason"] = (
                "repository documentation declares that this retained historical checkout is "
                "deprecated and has an active replacement"
            )
            return result
        commands, scan_error = quality_commands_from_worktree(
            worktree,
            run_id=f"{repository['repo_id']}-dynamic",
        )
        if scan_error is not None:
            result["status"] = "blocked"
            result["reason"] = f"target worktree command discovery failed: {scan_error}"
            return result
        result["command_discovery"] = "target_worktree"
        if not commands:
            if _documented_archival_repository(worktree):
                result["status"] = "not_applicable"
                result["reason"] = (
                    "repository documentation declares an archival generated snapshot with no "
                    "maintained executable quality surface"
                )
                return result
            result["status"] = "failed"
            result["reason"] = "no local quality commands were discovered on the exact target"
            return result
        dependency_source = _dependency_source(repository, worktree=worktree, default=source)
        dependency_setup = _prepare_dynamic_dependencies(
            worktree=worktree,
            source=dependency_source,
            local_source=_local_dependency_source(
                repository, worktree=worktree, default=dependency_source
            ),
            timeout_seconds=timeout_seconds,
        )
        dependency_cleanup_paths = [
            Path(path) for path in dependency_setup.pop("_cleanup_paths", [])
        ]
        result["dependency_setup"] = dependency_setup
        if dependency_setup["status"] not in {"passed", "not_required"}:
            result["status"] = str(dependency_setup["status"])
            result["reason"] = str(
                dependency_setup.get("reason", "dependency setup did not complete")
            )
            return result
        configured_gate_timeouts = _configured_gate_timeouts(worktree)
        result["timeout_ceiling_seconds"] = timeout_seconds
        result["configured_gate_timeouts"] = configured_gate_timeouts
        for command in commands:
            capability_id = str(command.get("id", "unknown"))
            command_timeout = _command_timeout(
                capability_id,
                configured_gate_timeouts,
                timeout_seconds,
            )
            if not _safe_dynamic_command(command):
                command_result = {
                    "command_id": command.get("id"),
                    "capability": command.get("id"),
                    "status": "not_applicable",
                    "reason": _dynamic_policy_block_reason(command),
                    "command_hash": hash_text(str(command.get("command", ""))),
                    "command_source": command.get("source"),
                    "timeout_seconds": command_timeout,
                }
            else:
                command_result = _run_dynamic_command(command, worktree, command_timeout)
            result["commands"].append(command_result)
            statuses.append(str(command_result["status"]))
        result["status"], aggregate_reason = _aggregate_dynamic_status(statuses)
        if aggregate_reason is not None:
            result["reason"] = aggregate_reason
    finally:
        cleanup = _git_command(source, "worktree", "remove", "--force", str(worktree), timeout=30)
        result["cleanup"] = {
            "status": "passed" if cleanup["returncode"] == 0 else "failed",
            "returncode": cleanup["returncode"],
        }
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)
        for path in reversed(dependency_cleanup_paths):
            remove_runtime_path(path)
    after = checkout_fingerprint(source)
    result["source_integrity_before"] = before
    result["source_integrity_after"] = after
    result["source_unchanged"] = before == after
    if not result["source_unchanged"]:
        result["status"] = "blocked"
        result["reason"] = "source checkout fingerprint changed during disposable verification"
    return result


def _run_dynamic_command(
    command: dict[str, Any], worktree: Path, timeout_seconds: int
) -> dict[str, Any]:
    return run_dynamic_command(command, worktree, timeout_seconds, runner=run_shell_command)


def _missing_runtime_requirement(command: str, stdout: str, stderr: str) -> str | None:
    combined = f"{stdout}\n{stderr}".lower()
    if "golangci-lint" in combined and "no such file or directory" in combined:
        return "required executable golangci-lint is unavailable in the bounded runtime"
    if "command not found" in combined or "executable file not found" in combined:
        return "a required executable is unavailable in the bounded runtime"
    if "public agent-config engine not found" in combined:
        return "the documented public agent-config sibling runtime is unavailable"
    return None


def _quality_commands_from_scan(repository: dict[str, Any]) -> list[dict[str, Any]]:
    scan = repository.get("scan")
    if not isinstance(scan, dict):
        return []
    commands = cast(dict[str, Any], scan).get("quality_commands")
    if not isinstance(commands, list):
        return []
    allowed_capabilities = {
        "lint",
        "typecheck",
        "tests",
        "formatter",
        "dead_code",
        "runtime_smoke",
        "build",
        "dependency_audit",
        "environment_contract",
        "security_secrets_scan",
    }
    # Keep every executable quality capability in the bounded dynamic set so
    # required security and dependency gates cannot be truncated by ordering.
    return [
        cast(dict[str, Any], item)
        for item in cast(list[object], commands)
        if isinstance(item, dict) and cast(dict[str, Any], item).get("id") in allowed_capabilities
    ][:12]


def _selection_reasons(
    *,
    repository: dict[str, Any],
    finding: dict[str, Any],
    target_head: object,
) -> list[str]:
    reasons: list[str] = []
    target = repository.get("target_branch")
    if not isinstance(target, dict) or cast(dict[str, Any], target).get("status") != "ready":
        reasons.append("target baseline is blocked or stale")
    if not target_head:
        reasons.append("target HEAD is missing")
    finding_items = cast(list[object], finding.get("findings", []))
    if any(
        cast(dict[str, Any], item).get("status") in {"unknown", "stale", "blocked"}
        for item in finding_items
        if isinstance(item, dict)
    ):
        reasons.append("static evidence is incomplete or stale")
    if any(
        cast(dict[str, Any], item).get("score", 0) < 2
        for item in finding_items
        if isinstance(item, dict) and cast(dict[str, Any], item).get("score") is not None
    ):
        reasons.append("a quality dimension is below discoverable maturity")
    return reasons


def _find_previous_dynamic(
    *,
    artifact_root: Path,
    repo_id: str,
    target_head: object,
    signature: str,
    as_of: str,
    max_age_days: int,
) -> dict[str, Any] | None:
    parent = artifact_root.parent
    if not parent.exists():
        return None
    current_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    for candidate in sorted(parent.iterdir(), reverse=True):
        if not candidate.is_dir() or candidate == artifact_root:
            continue
        finding_path = candidate / "findings" / f"{repo_id}.json"
        inventory_path = candidate / "inventory.json"
        if not finding_path.is_file() or not inventory_path.is_file():
            continue
        try:
            finding = _read_json(finding_path)
            inventory = _read_json(inventory_path)
            previous_as_of = datetime.fromisoformat(str(inventory["as_of"]).replace("Z", "+00:00"))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if current_as_of - previous_as_of > timedelta(days=max_age_days):
            continue
        dynamic = finding.get("dynamic")
        if not isinstance(dynamic, dict) or cast(dict[str, Any], dynamic).get("status") not in {
            "passed",
            "reused",
        }:
            continue
        dynamic_map = cast(dict[str, Any], dynamic)
        if (
            dynamic_map.get("target_head") != target_head
            or dynamic_map.get("signature") != signature
        ):
            continue
        return {
            "previous_audit_id": candidate.name,
            "target_head": target_head,
            "signature": signature,
            "commands": dynamic_map.get("commands", []),
        }
    return None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_command(cwd: Path, *args: str, timeout: int) -> dict[str, Any]:
    try:
        result = run_command(["git", *args], cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        return {"returncode": 124, "stdout": str(error.stdout or ""), "stderr": "timeout"}
    except OSError as error:
        return {"returncode": 1, "stdout": "", "stderr": str(error)}
    return {
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
    }
