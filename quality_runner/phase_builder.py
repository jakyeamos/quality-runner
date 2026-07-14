from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from quality_runner.schema_constants import PHASE_PLAN_SCHEMA

WAVE_BY_PRIORITY = {"high": 1, "medium": 2, "low": 3}
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def ordered_slices(slices: object) -> list[dict[str, Any]]:
    if not isinstance(slices, list):
        return []
    valid = [item for item in slices if isinstance(item, dict) and isinstance(item.get("id"), str)]
    indexed = list(enumerate(valid))
    indexed.sort(
        key=lambda item: (
            PRIORITY_ORDER.get(str(item[1].get("priority") or "medium").lower(), 1),
            item[0],
        )
    )
    return [item[1] for item in indexed]


def wave_by_slice(slices: list[dict[str, Any]]) -> dict[str, int]:
    by_id = {str(item["id"]): item for item in slices}
    resolved: dict[str, int] = {}
    visiting: set[str] = set()

    def resolve(slice_id: str) -> int:
        if slice_id in resolved:
            return resolved[slice_id]
        if slice_id in visiting:
            raise ValueError(f"remediation slice dependency cycle includes: {slice_id}")
        visiting.add(slice_id)
        item = by_id[slice_id]
        priority = str(item.get("priority") or "medium").lower()
        wave = WAVE_BY_PRIORITY.get(priority, 2)
        for dependency in _string_list(item.get("depends_on")):
            if dependency in by_id:
                wave = max(wave, resolve(dependency) + 1)
        visiting.remove(slice_id)
        resolved[slice_id] = wave
        return wave

    for slice_id in by_id:
        resolve(slice_id)
    return resolved


def build_phase_plan(
    *,
    phase: dict[str, Any],
    plan_number: int,
    slice_item: dict[str, Any],
    source: dict[str, Any],
    plan_ids_by_slice: dict[str, int],
    wave_by_slice: dict[str, int],
) -> dict[str, Any]:
    priority = str(slice_item.get("priority") or "medium").lower()
    finding_value = slice_item.get("findings")
    finding_items: list[object] = (
        [item for item in finding_value] if isinstance(finding_value, list) else []
    )
    finding_ids = [
        str(item["id"])
        for item in finding_items
        if isinstance(item, dict) and item.get("id")
    ]
    fingerprints = [
        str(item["fingerprint"])
        for item in finding_items
        if isinstance(item, dict) and item.get("fingerprint")
    ]
    depends_on = [
        f"{int(phase['number']):02d}-{plan_ids_by_slice[item]:02d}"
        for item in _string_list(slice_item.get("depends_on"))
        if item in plan_ids_by_slice
    ]
    source_info = source["source"] if isinstance(source.get("source"), dict) else {}
    return {
        "schema": PHASE_PLAN_SCHEMA,
        "phase": int(phase["number"]),
        "plan": plan_number,
        "id": f"{int(phase['number']):02d}-{plan_number:02d}",
        "title": str(slice_item.get("title") or slice_item.get("id")),
        "status": "planned",
        "wave": wave_by_slice.get(
            str(slice_item["id"]), WAVE_BY_PRIORITY.get(priority, 2)
        ),
        "depends_on": depends_on,
        "source": source_info,
        "source_slice_id": str(slice_item["id"]),
        "priority": priority,
        "finding_ids": finding_ids,
        "finding_fingerprints": fingerprints,
        "scope": slice_item.get("scope") if isinstance(slice_item.get("scope"), dict) else {},
        "tasks": _string_list(slice_item.get("actions")),
        "verification_gates": _string_list(slice_item.get("verification_gates")),
        "stop_conditions": _string_list(slice_item.get("stop_conditions")),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
