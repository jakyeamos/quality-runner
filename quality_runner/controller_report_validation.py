from __future__ import annotations

from typing import Any, cast

from quality_runner.schema_constants import CONTROLLER_REPORT_VALIDATION_SCHEMA

TERMINAL_STATUSES = {"ready-for-review", "blocked", "complete"}


def validate_controller_report(report: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    status = report.get("status")
    if status not in TERMINAL_STATUSES:
        errors.append("report status must be ready-for-review, blocked, or complete")

    for field in ("repo_path", "branch_name", "baseline_artifact_path"):
        if not _non_empty_string(report.get(field)):
            errors.append(f"{field} must be a non-empty string")

    if not isinstance(report.get("final_qr"), dict):
        errors.append("final_qr must be an object")
    if not isinstance(report.get("files_changed"), list):
        errors.append("files_changed must be a list")
    if not isinstance(report.get("verification"), list):
        errors.append("verification must be a list")
    if not isinstance(report.get("blockers"), list):
        errors.append("blockers must be a list")

    ignored_generated_artifacts = report.get("ignored_generated_artifacts")
    if ignored_generated_artifacts is not None and not _string_list(ignored_generated_artifacts):
        errors.append("ignored_generated_artifacts must be a list of non-empty strings")

    git_status = report.get("git_status_short")
    if not isinstance(git_status, str):
        errors.append("git_status_short must be a string")
    elif (
        status in {"complete", "ready-for-review"}
        and git_status.strip()
        and not _only_ignored_generated_artifacts(git_status, ignored_generated_artifacts)
    ):
        errors.append("completed reports must have a clean git_status_short field")

    if status == "complete":
        if not _non_empty_string(report.get("commit_hash")):
            errors.append("completed reports must include a commit_hash")
        if report.get("push_status") != "pushed":
            errors.append('completed reports must have push_status "pushed"')
    elif status == "blocked":
        blockers = report.get("blockers")
        if isinstance(blockers, list) and not blockers:
            errors.append("blocked reports must include at least one blocker")

    return {
        "schema": CONTROLLER_REPORT_VALIDATION_SCHEMA,
        "status": "rejected" if errors else "accepted",
        "errors": errors,
    }


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _only_ignored_generated_artifacts(git_status: str, ignored: object) -> bool:
    if not _string_list(ignored):
        return False
    ignored_paths = [item.rstrip("/") for item in cast(list[str], ignored)]
    lines = [line for line in git_status.splitlines() if line.strip()]
    if not lines:
        return True
    return all(_line_is_ignored(line, ignored_paths) for line in lines)


def _line_is_ignored(line: str, ignored_paths: list[str]) -> bool:
    path = line[3:].strip() if len(line) > 3 else line.strip()
    normalized = path.rstrip("/")
    return any(
        normalized == ignored or normalized.startswith(f"{ignored}/") for ignored in ignored_paths
    )
