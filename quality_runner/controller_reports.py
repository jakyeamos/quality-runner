from __future__ import annotations

from typing import Any

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

    git_status = report.get("git_status_short")
    if not isinstance(git_status, str):
        errors.append("git_status_short must be a string")
    elif status in {"complete", "ready-for-review"} and git_status.strip():
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


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)
