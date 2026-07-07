from __future__ import annotations

import json
import shlex
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner.controller_reports import (
    build_controller_report_from_summary,
    validate_controller_report,
)
from quality_runner.fleet_documents import write_fleet_documents
from quality_runner.workflow import refresh_payload

ROLLOUT_RESULT_SCHEMA = "quality-runner-rollout-result-v0.1"
ROLLOUT_LEDGER_SCHEMA = "quality-runner-rollout-ledger-v0.1"

RefreshCallback = Callable[..., dict[str, Any]]


def rollout_payload(
    *,
    repo_list_path: Path | None,
    repos: list[str],
    run_id_prefix: str | None,
    output_dir: Path | None,
    profile: str | None,
    ci_status_json: Path | None,
    timeout_seconds: int,
    workflow_timeout_seconds: int | None,
    verify_timeout_seconds: int | None,
    workflow_timeout_reason: str | None,
    total_timeout_seconds: int | None,
    total_timeout_reason: str | None,
    checkout_most_advanced_branch: bool,
    allow_mutating_gates: bool,
    refresh_callback: RefreshCallback = refresh_payload,
) -> dict[str, Any]:
    entries = _load_rollout_entries(repo_list_path=repo_list_path, repos=repos)
    if not entries:
        raise ValueError("rollout requires at least one repo from --repo or repo_list")

    resolved_run_id_prefix = run_id_prefix or _default_rollout_id()
    resolved_output_dir = (
        output_dir.expanduser().resolve()
        if output_dir
        else (Path.cwd() / ".quality-runner" / "rollouts" / resolved_run_id_prefix).resolve()
    )
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        results.append(
            _run_rollout_entry(
                entry=entry,
                index=index,
                run_id_prefix=resolved_run_id_prefix,
                output_dir=resolved_output_dir,
                profile=profile,
                ci_status_json=ci_status_json,
                timeout_seconds=timeout_seconds,
                workflow_timeout_seconds=workflow_timeout_seconds,
                verify_timeout_seconds=verify_timeout_seconds,
                workflow_timeout_reason=workflow_timeout_reason,
                total_timeout_seconds=total_timeout_seconds,
                total_timeout_reason=total_timeout_reason,
                checkout_most_advanced_branch=checkout_most_advanced_branch,
                allow_mutating_gates=allow_mutating_gates,
                refresh_callback=refresh_callback,
            )
        )

    fleet_documents = write_fleet_documents(output_dir=resolved_output_dir, results=results)
    ledger = {
        "schema": ROLLOUT_LEDGER_SCHEMA,
        "status": _rollout_status(results),
        "run_id_prefix": resolved_run_id_prefix,
        "output_dir": str(resolved_output_dir),
        "repo_count": len(entries),
        "fleet_documents": fleet_documents,
        "results": results,
    }
    ledger_path = resolved_output_dir / "rollout-ledger.json"
    _write_json(ledger_path, ledger)

    return {
        "schema": ROLLOUT_RESULT_SCHEMA,
        "status": ledger["status"],
        "run_id_prefix": resolved_run_id_prefix,
        "output_dir": str(resolved_output_dir),
        "ledger_path": str(ledger_path),
        "fleet_documents": fleet_documents,
        "repo_count": len(entries),
        "accepted_reports": sum(
            1 for result in results if result.get("report_status") == "accepted"
        ),
        "rejected_reports": sum(
            1 for result in results if result.get("report_status") == "rejected"
        ),
        "failed_repos": [
            result["repo_path"]
            for result in results
            if result.get("status") in {"error", "invalid-repo"}
        ],
        "results": results,
    }


def _run_rollout_entry(
    *,
    entry: dict[str, str],
    index: int,
    run_id_prefix: str,
    output_dir: Path,
    profile: str | None,
    ci_status_json: Path | None,
    timeout_seconds: int,
    workflow_timeout_seconds: int | None,
    verify_timeout_seconds: int | None,
    workflow_timeout_reason: str | None,
    total_timeout_seconds: int | None,
    total_timeout_reason: str | None,
    checkout_most_advanced_branch: bool,
    allow_mutating_gates: bool,
    refresh_callback: RefreshCallback,
) -> dict[str, Any]:
    repo_root = Path(entry["repo_path"]).expanduser().resolve()
    repo_name = entry.get("name") or repo_root.name
    repo_slug = _repo_slug(repo_name, fallback=f"repo-{index}")
    repo_run_id_prefix = entry.get("run_id_prefix") or f"{run_id_prefix}-{repo_slug}"
    report_path = output_dir / f"{index:03d}-{repo_slug}-controller-report.json"
    validation_path = output_dir / f"{index:03d}-{repo_slug}-controller-report-validation.json"

    if not repo_root.exists() or not repo_root.is_dir():
        error = f"repo root does not exist or is not a directory: {repo_root}"
        result = {
            "status": "invalid-repo",
            "repo_name": repo_name,
            "repo_slug": repo_slug,
            "repo_path": str(repo_root),
            "run_id_prefix": repo_run_id_prefix,
            "error": error,
        }
        _write_json(validation_path, _error_validation(error))
        return {**result, "validation_path": str(validation_path), "report_status": "rejected"}

    pre_head = _git_head(repo_root)
    pre_git_status_short = _git_status_short(repo_root)
    branch_name = _git_branch(repo_root)
    try:
        refresh = refresh_callback(
            repo_root=repo_root,
            run_id_prefix=repo_run_id_prefix,
            baseline_run_id=entry.get("baseline_run_id"),
            profile=profile,
            ci_status_json=ci_status_json,
            timeout_seconds=timeout_seconds,
            workflow_timeout_seconds=workflow_timeout_seconds,
            verify_timeout_seconds=verify_timeout_seconds,
            workflow_timeout_reason=workflow_timeout_reason,
            total_timeout_seconds=total_timeout_seconds,
            total_timeout_reason=total_timeout_reason,
            checkout_most_advanced_branch=checkout_most_advanced_branch,
            allow_mutating_gates=allow_mutating_gates,
        )
        summary = refresh.get("summary")
        if not isinstance(summary, dict):
            raise ValueError("refresh did not return a summary object")
        post_git_status_short = _git_status_short(repo_root)
        target_head = _git_head(repo_root)
        report = build_controller_report_from_summary(
            repo_path=str(repo_root),
            branch_name=branch_name,
            summary=summary,
            baseline_run_id=entry.get("baseline_run_id"),
            git_status_short=post_git_status_short,
            files_changed=_files_changed_since(pre_git_status_short, post_git_status_short),
            target_head=target_head,
            pre_head=pre_head,
            pre_git_status_short=pre_git_status_short,
            push_status="not-pushed",
            report_path=str(report_path),
            generation_command=_refresh_generation_command(
                repo_root=repo_root,
                repo_run_id_prefix=repo_run_id_prefix,
                baseline_run_id=entry.get("baseline_run_id"),
            ),
        )
        validation = validate_controller_report(report)
        _write_json(report_path, report)
        _write_json(validation_path, validation)
        return {
            "status": str(refresh.get("status") or summary.get("status") or "unknown"),
            "repo_name": repo_name,
            "repo_slug": repo_slug,
            "repo_path": str(repo_root),
            "branch_name": branch_name,
            "run_id_prefix": repo_run_id_prefix,
            "final_run_id": summary.get("run_id"),
            "classification": summary.get("recommended_classification"),
            "report_path": str(report_path),
            "validation_path": str(validation_path),
            "report_status": validation["status"],
            "validation_errors": validation["errors"],
            "artifact_path": summary.get("path"),
        }
    except Exception as error:
        post_git_status_short = _git_status_short(repo_root)
        failure_summary = {
            "run_id": f"{repo_run_id_prefix}-verify",
            "status": "blocked",
            "recommended_classification": "controller-refresh-error",
            "path": str(repo_root / ".quality-runner" / "runs" / f"{repo_run_id_prefix}-verify"),
        }
        report = build_controller_report_from_summary(
            repo_path=str(repo_root),
            branch_name=branch_name,
            summary=failure_summary,
            baseline_run_id=entry.get("baseline_run_id"),
            git_status_short=post_git_status_short,
            files_changed=_files_changed_since(pre_git_status_short, post_git_status_short),
            blockers=[f"Controller refresh failed before terminal evidence: {error}"],
            target_head=_git_head(repo_root),
            pre_head=pre_head,
            pre_git_status_short=pre_git_status_short,
            push_status="not-pushed",
            report_path=str(report_path),
            generation_command=_refresh_generation_command(
                repo_root=repo_root,
                repo_run_id_prefix=repo_run_id_prefix,
                baseline_run_id=entry.get("baseline_run_id"),
            ),
        )
        validation = validate_controller_report(report)
        _write_json(report_path, report)
        _write_json(validation_path, validation)
        return {
            "status": "error",
            "repo_name": repo_name,
            "repo_slug": repo_slug,
            "repo_path": str(repo_root),
            "branch_name": branch_name,
            "run_id_prefix": repo_run_id_prefix,
            "error": str(error),
            "report_path": str(report_path),
            "validation_path": str(validation_path),
            "report_status": validation["status"],
            "validation_errors": validation["errors"],
        }


def _load_rollout_entries(*, repo_list_path: Path | None, repos: list[str]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    if repo_list_path is not None:
        entries.extend(_parse_repo_list(repo_list_path.expanduser()))
    entries.extend({"repo_path": repo} for repo in repos)
    return entries


def _parse_repo_list(path: Path) -> list[dict[str, str]]:
    content = path.read_text(encoding="utf-8")
    stripped = content.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return _parse_json_repo_list(json.loads(content))
    entries: list[dict[str, str]] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(_parse_text_repo_line(line))
    return entries


def _parse_json_repo_list(value: object) -> list[dict[str, str]]:
    repos = value.get("repos") if isinstance(value, dict) else value
    if not isinstance(repos, list):
        raise ValueError("JSON repo list must be an array or an object with a repos array")
    entries: list[dict[str, str]] = []
    for item in repos:
        if isinstance(item, str):
            entries.append({"repo_path": item})
        elif isinstance(item, dict):
            repo_path = _string_value(item.get("repo_path")) or _string_value(item.get("path"))
            if not repo_path:
                raise ValueError("JSON repo entry must include repo_path or path")
            entry = {"repo_path": repo_path}
            for key in ("name", "baseline_run_id", "run_id_prefix"):
                value = _string_value(item.get(key))
                if value:
                    entry[key] = value
            entries.append(entry)
        else:
            raise ValueError("JSON repo entries must be strings or objects")
    return entries


def _parse_text_repo_line(line: str) -> dict[str, str]:
    parts = [part.strip() for part in line.split(",")] if "," in line else shlex.split(line)
    if not parts or not parts[0]:
        raise ValueError("repo list line must start with a repo path")
    entry = {"repo_path": parts[0]}
    if len(parts) > 1 and parts[1]:
        entry["baseline_run_id"] = parts[1]
    if len(parts) > 2 and parts[2]:
        entry["name"] = parts[2]
    return entry


def _default_rollout_id() -> str:
    return f"rollout-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def _rollout_status(results: list[dict[str, Any]]) -> str:
    if any(result.get("status") in {"error", "invalid-repo"} for result in results):
        return "completed-with-errors"
    if any(result.get("report_status") == "rejected" for result in results):
        return "completed-with-rejected-reports"
    return "completed"


def _repo_slug(value: str, *, fallback: str) -> str:
    slug = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or fallback


def _files_changed_since(pre_git_status_short: str, post_git_status_short: str) -> list[str]:
    pre_lines = set(_git_status_lines(pre_git_status_short))
    return [
        _git_status_path(line)
        for line in _git_status_lines(post_git_status_short)
        if line not in pre_lines and not _git_status_path(line).startswith(".quality-runner/")
    ]


def _git_status_lines(status: str) -> list[str]:
    return [line for line in status.splitlines() if line.strip()]


def _git_status_path(line: str) -> str:
    return line[3:].strip() if len(line) > 3 else line.strip()


def _git_branch(repo_root: Path) -> str:
    return _git_command(repo_root, ["branch", "--show-current"]) or "unknown"


def _git_status_short(repo_root: Path) -> str:
    return _git_command(repo_root, ["status", "--short"])


def _git_head(repo_root: Path) -> str:
    return _git_command(repo_root, ["rev-parse", "HEAD"])


def _git_command(repo_root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()


def _refresh_generation_command(
    *,
    repo_root: Path,
    repo_run_id_prefix: str,
    baseline_run_id: str | None,
) -> str:
    command = f"quality-runner refresh {repo_root} --run-id-prefix {repo_run_id_prefix} --json"
    if baseline_run_id:
        command += f" --baseline-run-id {baseline_run_id}"
    return command


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _error_validation(error: str) -> dict[str, Any]:
    return {
        "schema": "quality-runner-controller-report-validation-v0.1",
        "status": "rejected",
        "errors": [error],
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
