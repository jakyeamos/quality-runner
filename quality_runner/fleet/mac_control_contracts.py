from __future__ import annotations

from pathlib import Path
from typing import Any

MAC_CONTROL_MANIFEST_SCHEMA = "mac-control-task-manifest/v1"
MAC_CONTROL_EVIDENCE_SCHEMA = "mac-control-task-evidence/v1"
MAC_CONTROL_REPORT_SCHEMA = "pronto-mac-control-ideal-state/v1"
MAC_CONTROL_AUDIT_SCHEMA = "quality-runner-mac-control-audit/v1"
MAC_CONTROL_REPLAY_SCHEMA = "quality-runner-mac-control-replay/v1"
MAC_CONTROL_REPORT_RELATIVE_PATH = Path("current") / "mac-control-ideal-state.json"
MAC_CONTROL_SUMMARY_RELATIVE_PATH = Path("current") / "mac-control-summary.json"
MAC_CONTROL_DEFAULT_ROOT = Path("~/.quality-runner/fleet-audit")
MAC_CONTROL_MANIFEST_RELATIVE_PATH = Path(".mac-control") / "ideal-state.json"

CRITERIA = (
    "stable_identity",
    "correct_semantics",
    "observable_state",
    "useful_hierarchy",
    "efficient_navigation",
    "verifiable_outcomes",
    "route_flexibility",
    "stable_change_behavior",
)
OBSERVABLE_STATES = (
    "enabled",
    "focused",
    "selected",
    "expanded",
    "visible",
    "loading",
    "completed",
)
CHANGE_STATES = ("loading", "modal", "disabled", "permission_unavailable")
ROUTES = (
    "native_api",
    "adapter",
    "accessibility",
    "keyboard",
    "scrolling",
    "visual_fallback_approved",
)


class MacControlAuditError(ValueError):
    pass


def validate_manifest(manifest: object) -> list[str]:
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    errors: list[str] = []
    if manifest.get("schema") != MAC_CONTROL_MANIFEST_SCHEMA:
        errors.append(f"schema must be {MAC_CONTROL_MANIFEST_SCHEMA}")
    applicability = _normalize_applicability(manifest.get("applicability"))
    if applicability is None:
        errors.append("applicability must be applicable or not_applicable")
    if not _nonempty(manifest.get("repository_id")):
        errors.append("repository_id is required")
    if not _nonempty(manifest.get("repository_name")):
        errors.append("repository_name is required")
    if not _nonempty(manifest.get("applicability_reason")):
        errors.append("applicability_reason is required")
    if applicability == "not_applicable":
        if manifest.get("tasks") not in (None, []):
            errors.append("not_applicable manifests must not declare tasks")
        return errors
    criteria = manifest.get("criteria")
    if not isinstance(criteria, dict):
        errors.append("criteria must be an object")
    else:
        for criterion in CRITERIA:
            if criteria.get(criterion) is not True:
                errors.append(f"criteria.{criterion} must be true")
        for criterion in criteria:
            if criterion not in CRITERIA:
                errors.append(f"criteria contains unsupported key {criterion}")
    tasks = manifest.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("applicable manifests must declare at least one task")
        return errors
    task_ids: set[str] = set()
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{index}] must be an object")
            continue
        task_id = str(task.get("task_id", "")).strip()
        label = task_id or f"tasks[{index}]"
        if not task_id:
            errors.append(f"{label} requires task_id")
        elif task_id in task_ids:
            errors.append(f"task {task_id} is duplicated")
        task_ids.add(task_id)
        for key in (
            "stable_target_id",
            "hierarchy",
            "semantic_action",
            "observable_postcondition",
            "navigation_strategy",
            "selected_route",
        ):
            if not _nonempty(task.get(key)):
                errors.append(f"task {label} requires {key}")
        if str(task.get("navigation_strategy", "")).strip().casefold() in {
            "sequential_tabbing",
            "sequential tabbing",
        }:
            errors.append(f"task {label} must not rely on sequential tabbing")
        _require_values(
            task.get("observable_states"),
            OBSERVABLE_STATES,
            f"task {label} observable_states",
            errors,
        )
        _require_values(
            task.get("change_states"), CHANGE_STATES, f"task {label} change_states", errors
        )
        eligible = task.get("eligible_routes")
        if not isinstance(eligible, list) or not eligible:
            errors.append(f"task {label} requires eligible_routes")
        else:
            normalized_routes = {
                _normalize_token(item) for item in eligible if isinstance(item, str)
            }
            for route in normalized_routes - set(ROUTES):
                errors.append(f"task {label} has unsupported route {route}")
            if _normalize_token(task.get("selected_route")) not in normalized_routes:
                errors.append(f"task {label} selected_route must be eligible")
        accessibility = task.get("accessibility")
        if accessibility is not None and not isinstance(accessibility, dict):
            errors.append(f"task {label} accessibility must be an object")
        elif isinstance(accessibility, dict) and not any(
            _nonempty(accessibility.get(key)) for key in ("identifier", "label", "role")
        ):
            errors.append(f"task {label} accessibility needs identifier, label, or role")
    return errors


def task_entries(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    entries: list[dict[str, Any]] = []
    for task in value:
        if not isinstance(task, dict):
            continue
        entries.append(
            {
                "task_id": str(task.get("task_id", "")),
                "stable_target_id": str(task.get("stable_target_id", "")),
                "hierarchy": str(task.get("hierarchy", "")),
                "semantic_action": str(task.get("semantic_action", "")),
                "observable_postcondition": str(task.get("observable_postcondition", "")),
                "observable_states": string_list(task.get("observable_states")),
                "navigation_strategy": str(task.get("navigation_strategy", "")),
                "eligible_routes": string_list(task.get("eligible_routes")),
                "selected_route": str(task.get("selected_route", "")),
                "change_states": string_list(task.get("change_states")),
                "attempts": 0,
                "successes": 0,
                "evidence": [],
            }
        )
    return entries


def merge_task_evidence(tasks: list[dict[str, Any]], value: object, errors: list[str]) -> None:
    by_id = {task.get("task_id"): task for task in tasks}
    if not isinstance(value, list):
        return
    for item in value:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id", ""))
        task = by_id.get(task_id)
        if task is None:
            errors.append(f"evidence:unknown_task={task_id or 'unnamed'}")
            continue
        attempts = item.get("attempts")
        successes = item.get("successes")
        if isinstance(attempts, int) and attempts >= 0:
            task["attempts"] = attempts
        if isinstance(successes, int) and successes >= 0:
            task["successes"] = successes
        if isinstance(item.get("selected_route"), str) and item["selected_route"].strip():
            task["selected_route"] = item["selected_route"].strip()
        task["evidence"] = string_list(item.get("evidence"))


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalize_applicability(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip().casefold().replace("-", "_").replace(" ", "_")
    return token if token in {"applicable", "not_applicable"} else None


def normalize_token(value: object) -> str:
    return str(value).strip().casefold().replace("-", "_").replace(" ", "_")


def bool_mapping(value: object) -> dict[str, bool]:
    return (
        {str(key): child for key, child in value.items() if isinstance(child, bool)}
        if isinstance(value, dict)
        else {}
    )


def string_list(value: object) -> list[str]:
    return (
        sorted({item for item in value if isinstance(item, str) and item.strip()})
        if isinstance(value, list)
        else []
    )


def _nonempty(value: object) -> bool:
    return nonempty(value)


def _normalize_applicability(value: object) -> str | None:
    return normalize_applicability(value)


def _normalize_token(value: object) -> str:
    return normalize_token(value)


def _require_values(
    value: object, required: tuple[str, ...], label: str, errors: list[str]
) -> None:
    values = {normalize_token(item) for item in value} if isinstance(value, list) else set()
    for expected in required:
        if expected not in values:
            errors.append(f"{label} is missing {expected}")
