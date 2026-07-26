from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from quality_runner.artifacts import prepare_safe_directory
from quality_runner.fleet.contracts import digest, hash_text, redact_text
from quality_runner.fleet.discovery import checkout_fingerprint
from quality_runner.process_runner import run_shell_command


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
    target_state = target.get("target_state")
    target_head = target.get("head")
    signature = digest(
        {
            "repo": repository.get("repo_id"),
            "head": target_head,
            "quality_commands": finding.get("scan", {}).get("quality_commands", []),
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
    if not isinstance(target_state, dict) or target_state.get("status") != "ready":
        return {
            "status": "blocked",
            "selected": True,
            "selection_reasons": reasons or ["priority or incomplete evidence"],
            "reason": target.get("reason", "target branch is not ready"),
            "target_branch": target.get("branch"),
            "signature": signature,
        }
    source_checkout_id = target.get("checkout_id")
    source_checkout = next(
        (
            item
            for item in repository.get("checkouts", [])
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
    commands = _quality_commands_from_scan(repository)
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
    if not commands:
        result["reason"] = "no safe local quality commands were discovered"
        return result
    worktree = artifact_root / "worktrees" / str(repository["repo_id"])
    prepare_safe_directory(worktree.parent)
    before = checkout_fingerprint(source)
    if worktree.exists() or worktree.is_symlink():
        result["status"] = "blocked"
        result["reason"] = "runtime-owned disposable worktree path already exists"
        result["source_integrity_before"] = before
        return result
    setup = _git_command(source, "worktree", "add", "--detach", str(worktree), head, timeout=30)
    if setup["returncode"] != 0:
        result["status"] = "blocked"
        result["reason"] = redact_text(setup["stderr"] or setup["stdout"], root=source)[:500]
        result["source_integrity_before"] = before
        return result
    try:
        statuses: list[str] = []
        for command in commands:
            if not _safe_dynamic_command(command):
                command_result = {
                    "command_id": command.get("id"),
                    "capability": command.get("id"),
                    "status": "blocked",
                    "reason": "command is outside the local read-only dynamic allowlist",
                    "command_hash": hash_text(str(command.get("command", ""))),
                }
            else:
                command_result = _run_dynamic_command(command, worktree, timeout_seconds)
            result["commands"].append(command_result)
            statuses.append(str(command_result["status"]))
        if "timeout" in statuses:
            result["status"] = "timeout"
        elif "blocked" in statuses:
            result["status"] = "blocked"
        elif "failed" in statuses:
            result["status"] = "failed"
        elif statuses and all(status == "passed" for status in statuses):
            result["status"] = "passed"
        else:
            result["status"] = "unknown"
    finally:
        cleanup = _git_command(source, "worktree", "remove", "--force", str(worktree), timeout=30)
        result["cleanup"] = {
            "status": "passed" if cleanup["returncode"] == 0 else "failed",
            "returncode": cleanup["returncode"],
        }
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)
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
    command_text = str(command.get("command", ""))
    try:
        result = run_shell_command(command_text, cwd=worktree, timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        return {
            "command_id": command.get("id"),
            "capability": command.get("id"),
            "status": "timeout",
            "timeout_seconds": timeout_seconds,
            "command_hash": hash_text(command_text),
            "stdout_length": len(str(error.output or "")),
            "stderr_length": len(str(error.stderr or "")),
        }
    stdout = str(result.get("stdout", ""))
    stderr = str(result.get("stderr", ""))
    return {
        "command_id": command.get("id"),
        "capability": command.get("id"),
        "status": "passed" if result.get("returncode") == 0 else "failed",
        "returncode": result.get("returncode"),
        "command_hash": hash_text(command_text),
        "stdout_hash": hash_text(stdout),
        "stderr_hash": hash_text(stderr),
        "stdout_length": len(stdout),
        "stderr_length": len(stderr),
    }


def apply_dynamic_quality_evidence(result: dict[str, Any]) -> None:
    dynamic = result.get("dynamic")
    if not isinstance(dynamic, dict) or dynamic.get("status") not in {"passed", "reused"}:
        return
    for finding in result.get("findings", []):
        if isinstance(finding, dict) and finding.get("dimension") == "quality_commands":
            finding["score"] = 4
            finding["status"] = "validated"
            finding["message"] = (
                "Discovered local quality commands passed in a protected disposable worktree."
            )
            finding["evidence"].append(
                {"path": "dynamic disposable worktree", "detail": "all selected commands passed"}
            )
            break


def _quality_commands_from_scan(repository: dict[str, Any]) -> list[dict[str, Any]]:
    scan = repository.get("scan")
    if not isinstance(scan, dict):
        return []
    commands = scan.get("quality_commands")
    if not isinstance(commands, list):
        return []
    allowed_capabilities = {"lint", "typecheck", "tests", "formatter", "dead_code", "runtime_smoke"}
    return [
        item
        for item in commands
        if isinstance(item, dict) and item.get("id") in allowed_capabilities
    ][:8]


def _safe_dynamic_command(command: dict[str, Any]) -> bool:
    text = str(command.get("command", "")).lower()
    if not text:
        return False
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


def _selection_reasons(
    *,
    repository: dict[str, Any],
    finding: dict[str, Any],
    target_head: object,
) -> list[str]:
    reasons: list[str] = []
    target = repository.get("target_branch")
    if not isinstance(target, dict) or target.get("status") != "ready":
        reasons.append("target baseline is blocked or stale")
    if not target_head:
        reasons.append("target HEAD is missing")
    if any(
        item.get("status") in {"unknown", "stale", "blocked"}
        for item in finding.get("findings", [])
        if isinstance(item, dict)
    ):
        reasons.append("static evidence is incomplete or stale")
    if any(
        item.get("score", 0) < 2
        for item in finding.get("findings", [])
        if isinstance(item, dict) and item.get("score") is not None
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
        if not isinstance(dynamic, dict) or dynamic.get("status") not in {"passed", "reused"}:
            continue
        if dynamic.get("target_head") != target_head or dynamic.get("signature") != signature:
            continue
        return {
            "previous_audit_id": candidate.name,
            "target_head": target_head,
            "signature": signature,
            "commands": dynamic.get("commands", []),
        }
    return None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_command(cwd: Path, *args: str, timeout: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return {"returncode": 124, "stdout": str(error.stdout or ""), "stderr": "timeout"}
    except OSError as error:
        return {"returncode": 1, "stdout": "", "stderr": str(error)}
    return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
