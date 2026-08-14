from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from quality_runner.fleet.cache_design_measurement import (
    discover_candidates,
    measure_tree,
    surface_projection,
)

CACHE_DESIGN_ASSESSMENT_SCHEMA = "quality-runner-cache-design-assessment-v1"
DEFAULT_MAX_ENTRIES = 250_000
DEFAULT_MAX_SECONDS = 20.0
EQUIVALENCE_RECEIPT = Path(".quality-runner/cache-design-equivalence.json")


@dataclass(frozen=True)
class SurfaceSpec:
    path: str
    storage_class: str
    lifecycle: str
    source: str
    max_bytes: int | None = None
    max_entries: int | None = None
    max_age_days: int | None = None
    reason: str | None = None
    exclude: tuple[str, ...] = ()


_KNOWN_SURFACES = (
    SurfaceSpec(".quality-runner/cache", "tool_cache", "tool_managed", "quality-runner"),
    SurfaceSpec(".next/cache", "tool_cache", "tool_managed", "nextjs"),
    SurfaceSpec(".next", "build_output", "rebuildable", "nextjs", exclude=(".next/cache",)),
    SurfaceSpec(".turbo", "tool_cache", "tool_managed", "turborepo"),
    SurfaceSpec("target", "build_output", "rebuildable", "cargo"),
    SurfaceSpec("node_modules", "dependency_materialization", "tool_managed", "node"),
    SurfaceSpec(".venv", "dependency_materialization", "rebuildable", "python"),
    SurfaceSpec("venv", "dependency_materialization", "rebuildable", "python"),
    SurfaceSpec(".pytest_cache", "tool_cache", "tool_managed", "pytest"),
    SurfaceSpec(".ruff_cache", "tool_cache", "tool_managed", "ruff"),
    SurfaceSpec(".mypy_cache", "tool_cache", "tool_managed", "mypy"),
    SurfaceSpec(".cache", "tool_cache", "", "generic"),
    SurfaceSpec("dist", "build_output", "rebuildable", "generic"),
    SurfaceSpec("build", "build_output", "rebuildable", "generic"),
)
_CANDIDATE_NAMES = {".cache", "cache", "build", "dist", ".output", "__pycache__"}
_SKIP_DISCOVERY = {".git", ".hg", ".svn"}


def assess_cache_design(
    root: Path,
    config: dict[str, Any],
    as_of: str,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> dict[str, Any]:
    resolved = root.expanduser().resolve()
    started = time.monotonic()
    custom = _custom_specs(config)
    specs = _effective_specs(custom)
    surfaces: list[dict[str, Any]] = []
    visited_entries = 0
    complete = True
    warnings: list[str] = []
    known_roots: list[Path] = []

    for spec in specs:
        path = resolved / spec.path
        if not os.path.lexists(path) or path.is_symlink():
            if path.is_symlink():
                complete = False
                warnings.append(f"{spec.path}: symlinked derived-storage roots are not traversed")
            continue
        known_roots.append(path)
        remaining = max_entries - visited_entries
        measurement = measure_tree(
            resolved,
            path,
            excluded={resolved / item for item in spec.exclude},
            max_entries=max(remaining, 0),
            deadline=started + max_seconds,
        )
        visited_entries += int(measurement["visited_entries"])
        complete = complete and bool(measurement["complete"])
        warnings.extend(str(item) for item in measurement.pop("warnings"))
        surfaces.append(surface_projection(spec, measurement, as_of))
        if visited_entries >= max_entries or time.monotonic() >= started + max_seconds:
            complete = False
            warnings.append("derived-storage traversal budget was exhausted")
            break

    if complete:
        candidates, candidate_complete, candidate_entries, candidate_warnings = discover_candidates(
            resolved,
            known_roots,
            candidate_names=_CANDIDATE_NAMES,
            skip_names=_SKIP_DISCOVERY,
            max_entries=max(max_entries - visited_entries, 0),
            deadline=started + max_seconds,
        )
        visited_entries += candidate_entries
        complete = complete and candidate_complete
        warnings.extend(candidate_warnings)
        for candidate in candidates:
            measurement = measure_tree(
                resolved,
                candidate,
                excluded=set(),
                max_entries=max(max_entries - visited_entries, 0),
                deadline=started + max_seconds,
            )
            visited_entries += int(measurement["visited_entries"])
            complete = complete and bool(measurement["complete"])
            warnings.extend(str(item) for item in measurement.pop("warnings"))
            surfaces.append(
                surface_projection(_candidate_spec(resolved, candidate), measurement, as_of)
            )

    totals = _totals(surfaces)
    categories = _categories(surfaces)
    risk_flags = _risk_flags(surfaces, complete)
    receipt = _receipt_evidence(resolved, as_of)
    score, status, applicability, message = _score(surfaces, complete, risk_flags, receipt)
    return {
        "schema": CACHE_DESIGN_ASSESSMENT_SCHEMA,
        "status": status,
        "score": score,
        "applicability": applicability,
        "message": message,
        "as_of": as_of,
        "measurement_complete": complete,
        "traversal": {
            "entry_budget": max_entries,
            "visited_entries": visited_entries,
            "time_budget_seconds": max_seconds,
        },
        "totals": totals,
        "categories": categories,
        "surfaces": sorted(surfaces, key=lambda item: str(item["path"])),
        "risk_flags": risk_flags,
        "growth": receipt,
        "warnings": sorted(set(warnings)),
    }


def public_cache_design_projection(assessment: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": CACHE_DESIGN_ASSESSMENT_SCHEMA,
        "status": assessment.get("status", "unknown"),
        "score": assessment.get("score"),
        "measurement_complete": assessment.get("measurement_complete") is True,
        "totals": dict(assessment.get("totals", {})),
        "categories": dict(assessment.get("categories", {})),
        "risk_flags": list(assessment.get("risk_flags", [])),
        "growth": dict(assessment.get("growth", {})),
    }


def _candidate_spec(root: Path, candidate: Path) -> SurfaceSpec:
    relative = candidate.relative_to(root).as_posix()
    if candidate.name == "__pycache__":
        return SurfaceSpec(relative, "tool_cache", "rebuildable", "python")
    return SurfaceSpec(relative, "unclassified", "", "heuristic")


def _custom_specs(config: dict[str, Any]) -> list[SurfaceSpec]:
    section = config.get("cache_design")
    if not isinstance(section, dict):
        return []
    specs: list[SurfaceSpec] = []
    for item in section.get("paths", []):
        if not isinstance(item, dict):
            continue
        specs.append(
            SurfaceSpec(
                path=str(item["path"]),
                storage_class=str(item["class"]),
                lifecycle=str(item["lifecycle"]),
                source="repository_config",
                max_bytes=_optional_int(item.get("max_bytes")),
                max_entries=_optional_int(item.get("max_entries")),
                max_age_days=_optional_int(item.get("max_age_days")),
                reason=str(item["reason"]) if item.get("reason") else None,
            )
        )
    return specs


def _effective_specs(custom: list[SurfaceSpec]) -> list[SurfaceSpec]:
    overrides = {item.path: item for item in custom}
    known: list[SurfaceSpec] = []
    for item in _KNOWN_SURFACES:
        override = overrides.pop(item.path, None)
        known.append(
            SurfaceSpec(**{**override.__dict__, "exclude": item.exclude})
            if override is not None
            else item
        )
    specs = [*known, *sorted(overrides.values(), key=lambda item: item.path)]
    result: list[SurfaceSpec] = []
    for item in specs:
        prefix = f"{item.path}/"
        nested = tuple(candidate.path for candidate in specs if candidate.path.startswith(prefix))
        result.append(
            SurfaceSpec(
                **{
                    **item.__dict__,
                    "exclude": tuple(sorted(set(item.exclude) | set(nested))),
                }
            )
        )
    return result


def _score(
    surfaces: list[dict[str, Any]],
    complete: bool,
    risks: list[str],
    receipt: dict[str, Any],
) -> tuple[int | None, str, str, str]:
    if not complete:
        return (
            None,
            "unknown",
            "unknown",
            "Derived storage was found, but bounded read-only measurement is incomplete or ambiguous.",
        )
    if not surfaces:
        return None, "not_applicable", "not_applicable", "No derived-storage surface was detected."
    if "unclassified_storage" in risks:
        return (
            None,
            "unknown",
            "unknown",
            "Derived storage was found, but bounded read-only measurement is incomplete or ambiguous.",
        )
    if "durable_disposable_conflict" in risks:
        return (
            0,
            "absent",
            "applicable",
            "Durable state is mixed into a conventionally disposable path.",
        )
    if "policy_bound_exceeded" in risks or "unbounded_cache" in risks:
        return (
            1,
            "discoverable",
            "applicable",
            "Derived storage is classified, but a cache is unbounded or exceeds its declared lifecycle bound.",
        )
    if any(item["lifecycle"] == "rebuildable" for item in surfaces):
        return (
            2,
            "validated",
            "applicable",
            "Derived storage is classified and rebuildable, but one or more surfaces rely on manual lifecycle management.",
        )
    if receipt.get("qualifies_for_level_4") is True:
        return (
            4,
            "maintained",
            "applicable",
            "Cache lifecycle enforcement, growth evidence, and cold/warm equivalence are current.",
        )
    return (
        3,
        "maintained",
        "applicable",
        "Applicable derived-storage paths are tool-managed or explicitly bounded; equivalence history is not yet sufficient for level 4.",
    )


def _risk_flags(surfaces: list[dict[str, Any]], complete: bool) -> list[str]:
    risks: set[str] = set()
    if not complete:
        risks.add("measurement_incomplete")
    if any(item["class"] == "unclassified" for item in surfaces):
        risks.add("unclassified_storage")
    if any(item["lifecycle"] == "unbounded" and item["class"] == "tool_cache" for item in surfaces):
        risks.add("unbounded_cache")
    if any(item["bound_violations"] for item in surfaces):
        risks.add("policy_bound_exceeded")
    disposable_paths = {item.path for item in _KNOWN_SURFACES}
    if any(
        item["class"] == "durable_state" and item["path"] in disposable_paths for item in surfaces
    ):
        risks.add("durable_disposable_conflict")
    return sorted(risks)


def _totals(surfaces: list[dict[str, Any]]) -> dict[str, int]:
    fields = (
        "logical_bytes",
        "allocated_bytes",
        "exclusive_allocated_bytes",
        "shared_allocated_bytes",
        "file_count",
        "shared_file_count",
    )
    return {field: sum(int(item.get(field, 0)) for item in surfaces) for field in fields} | {
        "surface_count": len(surfaces)
    }


def _categories(surfaces: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for item in surfaces:
        category = str(item["class"])
        row = result.setdefault(
            category,
            {
                "surface_count": 0,
                "allocated_bytes": 0,
                "exclusive_allocated_bytes": 0,
                "file_count": 0,
            },
        )
        row["surface_count"] += 1
        row["allocated_bytes"] += int(item["allocated_bytes"])
        row["exclusive_allocated_bytes"] += int(item["exclusive_allocated_bytes"])
        row["file_count"] += int(item["file_count"])
    return dict(sorted(result.items()))


def _receipt_evidence(root: Path, as_of: str) -> dict[str, Any]:
    import json

    path = root / EQUIVALENCE_RECEIPT
    if not path.is_file() or path.is_symlink():
        return {"available": False, "qualifies_for_level_4": False, "snapshot_count": 0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False, "qualifies_for_level_4": False, "snapshot_count": 0}
    snapshots = payload.get("snapshots")
    valid_snapshots = (
        [item for item in snapshots if isinstance(item, dict) and item.get("observed_at")]
        if isinstance(snapshots, list)
        else []
    )
    allocated_delta = _snapshot_delta(valid_snapshots, "allocated_bytes")
    qualifies = bool(
        payload.get("schema") == "quality-runner-cache-design-equivalence/v1"
        and payload.get("automated_enforcement") is True
        and payload.get("cold_warm_equivalent") is True
        and payload.get("within_policy") is True
        and len(valid_snapshots) >= 2
        and _receipt_not_future(valid_snapshots[-1].get("observed_at"), as_of)
    )
    return {
        "available": True,
        "qualifies_for_level_4": qualifies,
        "snapshot_count": len(valid_snapshots),
        "allocated_bytes_delta": allocated_delta,
        "cache_hit_count_delta": _snapshot_delta(valid_snapshots, "cache_hit_count"),
        "cold_warm_equivalent": payload.get("cold_warm_equivalent") is True,
        "within_policy": payload.get("within_policy") is True,
        "automated_enforcement": payload.get("automated_enforcement") is True,
    }


def _snapshot_delta(snapshots: list[dict[str, Any]], key: str) -> int | None:
    if len(snapshots) < 2:
        return None
    before, after = snapshots[-2].get(key), snapshots[-1].get(key)
    if not isinstance(before, int) or isinstance(before, bool):
        return None
    if not isinstance(after, int) or isinstance(after, bool):
        return None
    return after - before


def _receipt_not_future(observed: object, as_of: str) -> bool:
    try:
        return datetime.fromisoformat(
            str(observed).replace("Z", "+00:00")
        ) <= datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError:
        return False


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
