from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner.phase_builder import build_phase_plan, ordered_slices, wave_by_slice
from quality_runner.phase_documents import (
    load_batch_result,
    render_plan,
    render_summary,
    render_verification,
)
from quality_runner.phase_sources import (
    load_json_artifact,
    load_optional_json,
    load_planning_source,
)
from quality_runner.phase_store import (
    load_phase_plans,
    load_plan_file,
    load_roadmap,
    load_state,
    phase_by_number,
    phase_directory,
    plan_file,
    require_plan_root,
    save_roadmap,
    save_state,
    summary_file,
    update_plan_file,
    verification_file,
    write_summary_file,
    write_verification_file,
)
from quality_runner.remediation_delta import build_remediation_delta
from quality_runner.schema_constants import (
    PHASE_RESULT_SCHEMA,
    PHASE_VERIFICATION_SCHEMA,
)


def initialize_plan(repo_root: Path) -> dict[str, Any]:
    from quality_runner.phase_store import initialize_plan_root

    result = initialize_plan_root(repo_root)
    return {
        "schema": PHASE_RESULT_SCHEMA,
        "status": "initialized",
        "implementation_allowed": False,
        **result,
    }


def plan_status(repo_root: Path) -> dict[str, Any]:
    roadmap = load_roadmap(repo_root)
    state = load_state(repo_root)
    phases: list[dict[str, Any]] = []
    for phase in roadmap.get("phases", []):
        if not isinstance(phase, dict):
            continue
        plans = load_phase_plans(repo_root, int(phase["number"]))
        phases.append(
            {
                "number": phase["number"],
                "slug": phase["slug"],
                "title": phase["title"],
                "status": phase.get("status", "planned"),
                "plan_count": len(plans),
                "plan_statuses": {str(plan["id"]): plan.get("status") for plan in plans},
            }
        )
    return {
        "schema": PHASE_RESULT_SCHEMA,
        "status": "ready",
        "implementation_allowed": False,
        "root": str(require_plan_root(repo_root)),
        "current_phase": state.get("current_phase"),
        "last_action": state.get("last_action"),
        "phases": phases,
    }


def add_phase(repo_root: Path, description: str) -> dict[str, Any]:
    require_plan_root(repo_root)
    title = description.strip()
    if not title:
        raise ValueError("phase description must not be empty")
    roadmap = load_roadmap(repo_root)
    phases = roadmap.get("phases")
    if not isinstance(phases, list):
        raise ValueError("QR roadmap phases must be a list")
    number = max((int(item.get("number", 0)) for item in phases if isinstance(item, dict)), default=0) + 1
    slug = _slug(title)
    phase = {
        "number": number,
        "slug": slug,
        "title": title,
        "goal": title,
        "status": "planned",
        "plan_ids": [],
        "updated_at": _now(),
    }
    phases.append(phase)
    roadmap["phases"] = phases
    save_roadmap(repo_root, roadmap)
    directory = phase_directory(repo_root, number)
    directory.mkdir(parents=True, exist_ok=True)
    context_path = directory / f"{number:02d}-CONTEXT.md"
    if not context_path.exists():
        context_path.write_text(
            f"# Phase {number:02d}: {title}\n\n## Goal\n\n{title}\n\n"
            "## Decisions\n\n- Record design and scope decisions here.\n",
            encoding="utf-8",
        )
    state = load_state(repo_root)
    state.update(
        {
            "status": "in_progress",
            "current_phase": number,
            "last_action": "phase-add",
            "updated_at": _now(),
        }
    )
    save_state(repo_root, state)
    return {
        "schema": PHASE_RESULT_SCHEMA,
        "status": "created",
        "implementation_allowed": False,
        "phase": phase,
        "phase_directory": str(directory),
        "context_path": str(context_path),
    }


def plan_phase(
    repo_root: Path,
    *,
    phase_number: int,
    run_id: str | None = None,
    handoff_json: Path | None = None,
) -> dict[str, Any]:
    roadmap = load_roadmap(repo_root)
    phase = phase_by_number(roadmap, phase_number)
    existing = load_phase_plans(repo_root, phase_number)
    if existing:
        return {
            "schema": PHASE_RESULT_SCHEMA,
            "status": "already-planned",
            "implementation_allowed": False,
            "phase": phase,
            "plans": existing,
        }
    source = load_planning_source(repo_root, run_id=run_id, handoff_json=handoff_json)
    slices = ordered_slices(source["slices"])
    if not slices:
        raise ValueError("planning source contains no remediation slices")
    directory = phase_directory(repo_root, phase_number)
    directory.mkdir(parents=True, exist_ok=True)
    plan_ids_by_slice = {str(item["id"]): index for index, item in enumerate(slices, start=1)}
    wave_by_slice_values = wave_by_slice(slices)
    plans: list[dict[str, Any]] = []
    for number, slice_item in enumerate(slices, start=1):
        plan = build_phase_plan(
            phase=phase,
            plan_number=number,
            slice_item=slice_item,
            source=source,
            plan_ids_by_slice=plan_ids_by_slice,
            wave_by_slice=wave_by_slice_values,
        )
        path = plan_file(repo_root, phase_number, number)
        path.write_text(render_plan(plan), encoding="utf-8")
        plans.append({**plan, "path": str(path)})
    phase["plan_ids"] = [plan["id"] for plan in plans]
    phase["source"] = source["source"]
    phase["status"] = "planned"
    phase["updated_at"] = _now()
    save_roadmap(repo_root, roadmap)
    state = load_state(repo_root)
    state.update(
        {
            "status": "in_progress",
            "current_phase": phase_number,
            "last_action": "phase-plan",
            "updated_at": _now(),
        }
    )
    save_state(repo_root, state)
    return {
        "schema": PHASE_RESULT_SCHEMA,
        "status": "planned",
        "implementation_allowed": False,
        "phase": phase,
        "source": source["source"],
        "plans": plans,
    }


def next_plan(repo_root: Path, phase_number: int | None = None) -> dict[str, Any]:
    roadmap = load_roadmap(repo_root)
    phases = roadmap.get("phases")
    if not isinstance(phases, list):
        raise ValueError("QR roadmap phases must be a list")
    selected: list[dict[str, Any]] = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        if phase_number is not None and phase.get("number") != phase_number:
            continue
        selected.extend(load_phase_plans(repo_root, int(phase["number"])))
    ready = [plan for plan in selected if _plan_ready(plan, selected)]
    if not ready:
        return {
            "schema": PHASE_RESULT_SCHEMA,
            "status": "complete-or-blocked",
            "implementation_allowed": False,
            "plan": None,
        }
    ready.sort(key=lambda item: (int(item.get("wave", 99)), int(item["plan"])))
    return {
        "schema": PHASE_RESULT_SCHEMA,
        "status": "ready",
        "implementation_allowed": False,
        "wave": ready[0].get("wave"),
        "plan": ready[0],
        "ready_plans": ready,
    }


def record_batch(
    repo_root: Path, *, phase_number: int, plan_number: int, result_file: Path
) -> dict[str, Any]:
    plan_path = plan_file(repo_root, phase_number, plan_number)
    plan = load_plan_file(plan_path)
    result = load_batch_result(result_file)
    plan["status"] = _result_plan_status(result["status"])
    plan["last_result"] = result
    plan["updated_at"] = _now()
    update_plan_file(plan_path, plan)
    summary_path = summary_file(repo_root, phase_number, plan_number)
    write_summary_file(summary_path, result, render_summary(plan, result))
    _update_phase_tracking(repo_root, phase_number, "phase-record-batch")
    return {
        "schema": PHASE_RESULT_SCHEMA,
        "status": "recorded",
        "implementation_allowed": False,
        "plan": plan,
        "summary_path": str(summary_path),
    }


def update_phase(
    repo_root: Path, *, phase_number: int, baseline_run_id: str, run_id: str
) -> dict[str, Any]:
    plans = load_phase_plans(repo_root, phase_number)
    delta = _load_or_build_delta(repo_root, baseline_run_id=baseline_run_id, run_id=run_id)
    resolved = _finding_refs(delta.get("findings", {}).get("resolved"))
    persisted = _finding_refs(delta.get("findings", {}).get("persisted"))
    new_records = _finding_records(delta.get("findings", {}).get("new"))
    current_verification = _nested_object(delta, "verification", "current")
    blocked = _verification_blocked(current_verification)
    updated: list[dict[str, Any]] = []
    for plan in plans:
        required = set(str(item) for item in plan.get("finding_fingerprints", []))
        if required and blocked:
            plan["status"] = "blocked"
            plan["evidence_status"] = "blocked"
        elif required and required <= resolved:
            plan["status"] = "verified"
            plan["evidence_status"] = "resolved"
        elif required & persisted:
            plan["status"] = "blocked" if blocked else "in_progress"
            plan["evidence_status"] = "blocked" if blocked else "persisted"
        plan["evidence_update"] = {
            "baseline_run_id": baseline_run_id,
            "run_id": run_id,
            "resolved": sorted(required & resolved),
            "persisted": sorted(required & persisted),
            "blocked": blocked,
            "updated_at": _now(),
        }
        plan["updated_at"] = _now()
        update_plan_file(Path(plan["path"]), plan)
        updated.append(plan)
    state = load_state(repo_root)
    previous_value = state.get("unplanned_findings")
    previous: list[object] = (
        [item for item in previous_value if isinstance(item, dict)]
        if isinstance(previous_value, list)
        else []
    )
    state["unplanned_findings"] = _unique_finding_refs([*previous, *new_records])
    state.update({"current_phase": phase_number, "last_action": "phase-update", "updated_at": _now()})
    save_state(repo_root, state)
    _update_phase_tracking(repo_root, phase_number, "phase-update")
    return {
        "schema": PHASE_RESULT_SCHEMA,
        "status": "blocked" if blocked else "updated",
        "implementation_allowed": False,
        "phase": phase_number,
        "run_id": run_id,
        "baseline_run_id": baseline_run_id,
        "plans": updated,
        "new_findings": new_records,
        "resolved_findings": sorted(resolved),
        "persisted_findings": sorted(persisted),
        "verification": current_verification,
    }


def verify_phase(repo_root: Path, *, phase_number: int, run_id: str) -> dict[str, Any]:
    plans = load_phase_plans(repo_root, phase_number)
    run_dir = repo_root / ".quality-runner" / "runs" / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"QR evidence run does not exist: {run_dir}")
    unresolved: list[str] = []
    failed: list[str] = []
    for plan in plans:
        if plan.get("status") in {"blocked", "failed"}:
            failed.append(str(plan["id"]))
        if plan.get("status") not in {"verified", "complete", "skipped"}:
            unresolved.append(str(plan["id"]))
    delta = load_optional_json(run_dir / "remediation-delta.json")
    gate = load_optional_json(run_dir / "gate-verification.json")
    delta_verification = _nested_object(delta, "verification", "current")
    if delta_verification and _verification_blocked(delta_verification):
        failed.append("remediation-delta-verification")
    if _verification_blocked(_gate_state(gate)):
        failed.append("gate-verification")
    status = "passed" if not unresolved and not failed else "failed"
    payload = {
        "schema": PHASE_VERIFICATION_SCHEMA,
        "status": status,
        "phase": phase_number,
        "run_id": run_id,
        "plan_ids": [str(plan["id"]) for plan in plans],
        "verified_plan_ids": [
            str(plan["id"]) for plan in plans if plan.get("status") in {"verified", "complete", "skipped"}
        ],
        "unresolved_plan_ids": unresolved,
        "failed_checks": failed,
        "implementation_allowed": False,
        "updated_at": _now(),
    }
    path = verification_file(repo_root, phase_number)
    write_verification_file(path, payload, render_verification(payload))
    return {**payload, "verification_path": str(path)}


def close_phase(repo_root: Path, *, phase_number: int, run_id: str) -> dict[str, Any]:
    verification = verify_phase(repo_root, phase_number=phase_number, run_id=run_id)
    if verification["status"] != "passed":
        return {
            "schema": PHASE_RESULT_SCHEMA,
            "status": "blocked",
            "implementation_allowed": False,
            "verification": verification,
        }
    roadmap = load_roadmap(repo_root)
    phase = phase_by_number(roadmap, phase_number)
    phase["status"] = "complete"
    phase["completed_run_id"] = run_id
    phase["updated_at"] = _now()
    save_roadmap(repo_root, roadmap)
    state = load_state(repo_root)
    state.update(
        {
            "status": "complete",
            "current_phase": phase_number,
            "last_action": "phase-close",
            "updated_at": _now(),
        }
    )
    save_state(repo_root, state)
    return {
        "schema": PHASE_RESULT_SCHEMA,
        "status": "closed",
        "implementation_allowed": False,
        "phase": phase,
        "verification": verification,
    }


def _load_or_build_delta(repo_root: Path, *, baseline_run_id: str, run_id: str) -> dict[str, Any]:
    path = repo_root / ".quality-runner" / "runs" / run_id / "remediation-delta.json"
    if path.exists():
        return load_json_artifact(path)
    return build_remediation_delta(
        repo_root=repo_root, baseline_run_id=baseline_run_id, current_run_id=run_id
    )


def _nested_object(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: object = payload
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _plan_ready(plan: dict[str, Any], all_plans: list[dict[str, Any]]) -> bool:
    if plan.get("status") not in {"planned", "in_progress"}:
        return False
    by_id = {str(item["id"]): item for item in all_plans}
    return all(by_id.get(str(dep), {}).get("status") in {"verified", "complete", "skipped"} for dep in plan.get("depends_on", []))


def _result_plan_status(status: str) -> str:
    return {"complete": "complete", "blocked": "blocked", "failed": "blocked", "skipped": "skipped", "in_progress": "in_progress"}[status]


def _verification_blocked(payload: object) -> bool:
    if not isinstance(payload, dict):
        return True
    status = payload.get("status")
    return status in {"failed", "blocked", "error"} or bool(payload.get("blockers")) or bool(payload.get("failure_type"))


def _gate_state(payload: dict[str, Any]) -> dict[str, Any]:
    return {"status": payload.get("status", "unavailable"), "blockers": payload.get("blockers", []), "failure_type": payload.get("failure_type")}


def _finding_refs(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item.get("fingerprint")) for item in value if isinstance(item, dict) and item.get("fingerprint")}


def _finding_records(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        item
        for item in value
        if isinstance(item, dict) and isinstance(item.get("fingerprint"), str)
    ]


def _unique_finding_refs(values: list[object]) -> list[dict[str, Any]]:
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


def _update_phase_tracking(repo_root: Path, phase_number: int, action: str) -> None:
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
    phase["updated_at"] = _now()
    save_roadmap(repo_root, roadmap)
    state = load_state(repo_root)
    state.update(
        {
            "status": phase["status"] if phase["status"] in {"blocked", "complete"} else "in_progress",
            "current_phase": phase_number,
            "last_action": action,
            "updated_at": _now(),
        }
    )
    save_state(repo_root, state)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "phase"


def _now() -> str:
    return datetime.now(UTC).isoformat()
