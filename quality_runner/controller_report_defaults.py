from __future__ import annotations

from pathlib import Path
from typing import Any, cast


def controller_command_environment(repo_path: str) -> dict[str, str]:
    cache_root = Path(repo_path) / ".quality-runner" / "cache"
    return {
        "UV_CACHE_DIR": str(cache_root / "uv"),
        "XDG_CACHE_HOME": str(cache_root / "xdg"),
    }


def normalized_controller_command_environment(
    report: dict[str, Any], *, repo_path: str
) -> dict[str, str]:
    environment = report.get("controller_command_environment")
    environment_map = _dict(environment)
    if environment_map is not None:
        return {
            key: value
            for key, value in environment_map.items()
            if isinstance(value, str) and key and value
        }
    return controller_command_environment(repo_path or ".")


def normalized_controller_status_recommendation(
    report: dict[str, Any],
    *,
    status: str,
    final_qr: dict[str, Any],
) -> dict[str, str]:
    recommendation = report.get("controller_status_recommendation")
    recommendation_map = _dict(recommendation)
    if recommendation_map is not None:
        raw_status = recommendation_map.get("status")
        reason = recommendation_map.get("reason")
        if isinstance(raw_status, str) and isinstance(reason, str) and raw_status:
            return {"status": raw_status, "reason": reason}
    classification = first_string(final_qr.get("classification"))
    final_status = first_string(final_qr.get("status"))
    return {
        "status": status,
        "reason": (
            f"normalized from final_qr status {final_status or 'unknown'}"
            + (f" ({classification})" if classification else "")
        ),
    }


def controller_status_recommendation(
    final_qr: dict[str, Any],
    *,
    commit_hash: str | None,
    commit_created_by_task: bool,
    push_status: str,
) -> dict[str, str]:
    if final_qr_clean(final_qr):
        if commit_hash and commit_created_by_task and push_status == "pushed":
            return {
                "status": "complete",
                "reason": "final QR is clean and the task-created commit was pushed",
            }
        return {
            "status": "ready-for-review",
            "reason": "final QR is clean but no task-created pushed commit is recorded",
        }
    status = first_string(final_qr.get("status"))
    classification = first_string(final_qr.get("classification"))
    return {
        "status": "blocked",
        "reason": (
            f"final QR status {status or 'unknown'} requires controller review"
            + (f" ({classification})" if classification else "")
        ),
    }


def inferred_blockers(final_qr: dict[str, Any]) -> list[str]:
    classification = first_string(
        final_qr.get("classification"),
        final_qr.get("recommended_classification"),
    )
    status = first_string(final_qr.get("status"))
    if final_qr_clean(final_qr):
        return []

    blockers: list[str] = []
    blocker_classes = string_values(final_qr.get("blocker_classes"))
    details: list[str] = []
    if status:
        details.append(f"status={status}")
    if classification:
        details.append(f"classification={classification}")
    if blocker_classes:
        details.append(f"blocker_classes={', '.join(blocker_classes)}")
    if details:
        blockers.append(f"Final QR is not clean: {'; '.join(details)}.")

    missing = string_values(final_qr.get("missing_capabilities"))
    if missing:
        blockers.append(f"Missing capabilities remain: {', '.join(missing)}.")

    failed_gates = gate_descriptions(final_qr.get("gate_results"), statuses={"failed"})
    if failed_gates:
        blockers.append(f"Failed gates: {', '.join(failed_gates)}.")

    skipped_gates = gate_descriptions(
        final_qr.get("gate_results"),
        skip_types={
            "mutating-gate-not-run",
            "dependency-setup-blocked",
            "execution-consent-required",
        },
    )
    if skipped_gates:
        blockers.append(f"Skipped or blocked gates: {', '.join(skipped_gates)}.")

    findings_total = final_qr.get("findings_total")
    if isinstance(findings_total, int) and findings_total > 0:
        blockers.append(f"Structural findings remain: {findings_total}.")

    failure_type = first_string(final_qr.get("failure_type"))
    if failure_type == "workflow-timeout":
        timeout_blockers = workflow_timeout_blockers(final_qr.get("timeout_diagnostics"))
        if timeout_blockers:
            blockers.extend(timeout_blockers)
        elif not any("workflow-timeout" in blocker for blocker in blockers):
            blockers.append("Workflow timeout prevented complete evidence collection.")

    return blockers or ([classification] if classification else [status] if status else [])


def workflow_timeout_blockers(timeout_diagnostics: object) -> list[str]:
    diagnostics = _dict(timeout_diagnostics)
    if diagnostics is None:
        return []
    blockers: list[str] = []
    timeout_scope = first_string(diagnostics.get("timeout_scope"))
    last_directory = first_string(diagnostics.get("last_directory"))
    visited_paths = diagnostics.get("visited_paths")
    scan_activity = _dict(diagnostics.get("scan_activity"))
    activity_path = (
        scan_activity.get("path")
        if scan_activity is not None and isinstance(scan_activity.get("path"), str)
        else None
    )
    if timeout_scope and isinstance(visited_paths, int) and (last_directory or activity_path):
        if (
            scan_activity is not None
            and scan_activity.get("kind") == "excluded-directory-estimation"
            and activity_path
        ):
            blockers.append(
                f"Workflow timeout: {timeout_scope} timed out while estimating excluded "
                f"directory {scan_activity['path']} (not actual scan work) after "
                f"{visited_paths} visited paths."
            )
        else:
            blockers.append(
                f"Workflow timeout: {timeout_scope} timed out at {last_directory or activity_path} "
                f"after {visited_paths} visited paths."
            )
    recommendations = diagnostics.get("pruning_recommendations")
    for recommendation in _dict_list(cast(object, recommendations)):
        pattern = recommendation.get("pattern")
        if isinstance(pattern, str) and pattern:
            blockers.append(f"Suggested scan exclusion: {pattern}.")
    return blockers


def repo_state(
    *,
    pre_head: str | None,
    post_head: str | None,
    pre_git_status_short: str | None,
    post_git_status_short: str,
    concurrency_note: str | None,
) -> dict[str, Any]:
    return compact(
        {
            "pre_head": pre_head,
            "post_head": post_head,
            "pre_git_status_short": pre_git_status_short,
            "post_git_status_short": post_git_status_short,
            "concurrency_note": concurrency_note,
            "dirty_state": dirty_state_groups(
                pre_git_status_short=pre_git_status_short or "",
                post_git_status_short=post_git_status_short,
            ),
        }
    )


def dirty_state_groups(
    *,
    pre_git_status_short: str,
    post_git_status_short: str,
) -> dict[str, list[str]]:
    pre_lines = git_status_lines(pre_git_status_short)
    post_lines = git_status_lines(post_git_status_short)
    pre_line_set = set(pre_lines)
    return {
        "pre_existing_dirty": pre_lines,
        "quality_runner_artifacts": [
            line for line in post_lines if git_status_path(line).startswith(".quality-runner/")
        ],
        "post_command_artifacts": [
            line
            for line in post_lines
            if line not in pre_line_set and not git_status_path(line).startswith(".quality-runner/")
        ],
    }


def final_qr_clean(final_qr: object) -> bool:
    final_qr_map = _dict(final_qr)
    if final_qr_map is None:
        return False
    status = str(final_qr_map.get("status") or "")
    classification = str(
        final_qr_map.get("classification") or final_qr_map.get("recommended_classification") or ""
    )
    return status in {"clean", "passed"} or classification == "clean"


def first_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def string_values(value: object) -> list[str]:
    return (
        [item for item in cast(list[Any], value) if isinstance(item, str) and item]
        if isinstance(value, list)
        else []
    )


def gate_descriptions(
    value: object,
    *,
    statuses: set[str] | None = None,
    skip_types: set[str] | None = None,
) -> list[str]:
    if not isinstance(value, list):
        return []
    descriptions: list[str] = []
    for gate in _dict_list(cast(object, value)):
        status = first_string(gate.get("status"))
        skip_type = first_string(gate.get("skip_type"))
        if statuses is not None and status not in statuses:
            continue
        if skip_types is not None and skip_type not in skip_types:
            continue
        gate_id = first_string(gate.get("id")) or "unknown"
        failure_type = first_string(gate.get("failure_type"))
        if failure_type:
            descriptions.append(f"{gate_id} ({failure_type})")
        elif skip_type:
            descriptions.append(f"{gate_id} ({skip_type})")
        else:
            descriptions.append(gate_id)
    return descriptions


def git_status_lines(status: str) -> list[str]:
    return [line for line in status.splitlines() if line.strip()]


def git_status_path(line: str) -> str:
    return line[3:].strip() if len(line) > 3 else line.strip()


def compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "", [])}


def _dict(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in cast(list[Any], value) if isinstance(item, dict)]
