from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def load_planning_source(
    repo_root: Path,
    *,
    run_id: str | None,
    handoff_json: Path | None,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    if run_id is not None:
        run_dir = repo_root / ".quality-runner" / "runs" / run_id
        plan_path = run_dir / "remediation-plan.json"
        handoff_path = run_dir / "agent-handoff.json"
        plan = load_json_artifact(plan_path) if plan_path.exists() else {}
        handoff = load_json_artifact(handoff_path) if handoff_path.exists() else {}
        return _source_payload(
            plan,
            handoff,
            run_id=run_id,
            handoff_path=handoff_path,
            plan_path=plan_path if plan else None,
            candidate_id=candidate_id,
        )
    if handoff_json is None:
        raise ValueError("phase plan requires --run-id or --handoff-json")
    raw_path = handoff_json.expanduser()
    if raw_path.is_symlink() or not raw_path.is_file():
        raise ValueError(f"handoff JSON must be a regular file: {raw_path}")
    path = raw_path.resolve()
    handoff = load_json_artifact(path)
    handoff_data = cast(dict[str, object], handoff)
    artifact_paths = handoff_data.get("artifact_paths")
    plan: dict[str, Any] = {}
    plan_path: Path | None = None
    if isinstance(artifact_paths, dict):
        plan_path_value = cast(dict[str, object], artifact_paths).get("remediation_plan_json")
        if isinstance(plan_path_value, str):
            candidate = Path(plan_path_value).expanduser()
            if not candidate.is_absolute():
                candidate = path.parent / candidate
            if candidate.is_symlink():
                raise ValueError(f"remediation plan must be a regular file: {candidate}")
            if candidate.exists():
                plan_path = candidate.resolve()
                plan = load_json_artifact(plan_path)
    return _source_payload(
        plan,
        handoff,
        run_id=handoff_data.get("run_id"),
        handoff_path=path,
        plan_path=plan_path,
        candidate_id=candidate_id,
    )


def load_json_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required JSON artifact does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact must contain an object: {path}")
    return cast(dict[str, Any], payload)


def load_optional_json(path: Path) -> dict[str, Any]:
    return load_json_artifact(path) if path.exists() else {}


def _source_payload(
    plan: dict[str, Any],
    handoff: dict[str, Any],
    *,
    run_id: object,
    handoff_path: Path,
    plan_path: Path | None,
    candidate_id: str | None,
) -> dict[str, Any]:
    plan_data = cast(dict[str, object], plan)
    handoff_data = cast(dict[str, object], handoff)
    phase_candidate_value = plan_data.get("phase_candidates")
    phase_candidates = (
        cast(list[object], phase_candidate_value) if isinstance(phase_candidate_value, list) else []
    )
    domain_slices: list[dict[str, Any]] = []
    for raw_item in phase_candidates:
        if isinstance(raw_item, dict):
            item = cast(dict[str, Any], raw_item)
            if isinstance(item.get("id"), str):
                domain_slices.append(item)
    if candidate_id is not None:
        if not domain_slices:
            raise ValueError(f"planning source has no domain phase candidate: {candidate_id}")
        domain_slices = [item for item in domain_slices if item.get("id") == candidate_id]
        if not domain_slices:
            raise ValueError(f"planning source has no domain phase candidate: {candidate_id}")
    legacy_value = plan_data.get("slices")
    legacy_slices = cast(list[object], legacy_value) if isinstance(legacy_value, list) else []
    slices: list[object] = cast(list[object], domain_slices) if domain_slices else legacy_slices
    next_slice = handoff_data.get("next_slice")
    if not slices and isinstance(next_slice, dict):
        slices = [next_slice]
    if not slices:
        raise ValueError("planning source contains no remediation slices")
    normalized_slices: list[dict[str, Any]] = []
    for item in slices:
        if not isinstance(item, dict):
            continue
        item_data = cast(dict[str, Any], item)
        if isinstance(item_data.get("id"), str):
            normalized_slices.append(item_data)
    return {
        "slices": [
            *normalized_slices,
        ],
        "planning_mode": "domain" if domain_slices else "forensic",
        "source": {
            "run_id": run_id if isinstance(run_id, str) else None,
            "handoff_json": str(handoff_path),
            "remediation_plan_json": str(plan_path) if plan_path is not None else None,
            **({"candidate_id": candidate_id} if candidate_id is not None else {}),
        },
    }
