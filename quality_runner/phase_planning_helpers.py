from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner.phase_sources import load_json_artifact
from quality_runner.phase_store import (
    load_phase_plans,
    load_roadmap,
    load_state,
    phase_by_number,
    save_roadmap,
    save_state,
)
from quality_runner.remediation_delta import build_remediation_delta


def load_or_build_delta(repo_root: Path, *, baseline_run_id: str, run_id: str) -> dict[str, Any]:
    path = repo_root / ".quality-runner" / "runs" / run_id / "remediation-delta.json"
    if path.exists():
        return load_json_artifact(path)
    return build_remediation_delta(
        repo_root=repo_root, baseline_run_id=baseline_run_id, current_run_id=run_id
    )


def nested_object(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def plan_ready(plan: dict[str, Any], all_plans: list[dict[str, Any]]) -> bool:
    if plan.get("status") not in {"planned", "in_progress"}:
        return False
    by_id = {str(item["id"]): item for item in all_plans}
    return all(
        by_id.get(str(dep), {}).get("status") in {"verified", "complete", "skipped"}
        for dep in plan.get("depends_on", [])
    )


def result_plan_status(status: str) -> str:
    return {
        "complete": "complete",
        "blocked": "blocked",
        "failed": "blocked",
        "skipped": "skipped",
        "in_progress": "in_progress",
    }[status]


def verification_blocked(payload: object) -> bool:
    if not isinstance(payload, dict):
        return True
    status = payload.get("status")
    return (
        status in {"failed", "blocked", "error"}
        or bool(payload.get("blockers"))
        or bool(payload.get("failure_type"))
    )


def gate_state(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status", "unavailable"),
        "blockers": payload.get("blockers", []),
        "failure_type": payload.get("failure_type"),
    }


def finding_refs(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {
        str(item.get("fingerprint"))
        for item in value
        if isinstance(item, dict) and item.get("fingerprint")
    }


def finding_records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, dict) and isinstance(item.get("fingerprint"), str)
    ]


def unique_finding_refs(values: list[object]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict) or not value.get("fingerprint"):
            continue
        fingerprint = str(value["fingerprint"])
        if fingerprint not in seen:
            seen.add(fingerprint)
            result.append(value)
    return result


def update_phase_tracking(repo_root: Path, phase_number: int, action: str) -> None:
    roadmap = load_roadmap(repo_root)
    phase = phase_by_number(roadmap, phase_number)
    plans = load_phase_plans(repo_root, phase_number)
    statuses = {str(plan.get("status")) for plan in plans}
    phase["status"] = (
        "blocked"
        if "blocked" in statuses
        else "complete"
        if plans and statuses <= {"complete", "verified", "skipped"}
        else "in_progress"
    )
    phase["plan_ids"] = [str(plan["id"]) for plan in plans]
    phase["updated_at"] = now()
    save_roadmap(repo_root, roadmap)
    state = load_state(repo_root)
    state.update(
        {
            "status": phase["status"]
            if phase["status"] in {"blocked", "complete"}
            else "in_progress",
            "current_phase": phase_number,
            "last_action": action,
            "updated_at": now(),
        }
    )
    save_state(repo_root, state)


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "phase"


def now() -> str:
    return datetime.now(UTC).isoformat()
