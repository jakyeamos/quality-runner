from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, cast

CACHE_DESIGN_CLASSES = {
    "tool_cache",
    "build_output",
    "dependency_materialization",
    "durable_state",
}
CACHE_DESIGN_LIFECYCLES = {"tool_managed", "bounded", "rebuildable", "durable"}
_BOUND_FIELDS = ("max_bytes", "max_entries", "max_age_days")
_KNOWN_DISPOSABLE_PATHS = {
    ".quality-runner/cache",
    ".next",
    ".next/cache",
    ".turbo",
    ".cache",
    ".venv",
    "venv",
    "build",
    "dist",
    "node_modules",
    "target",
}


def parse_cache_design_section(value: object, warnings: list[dict[str, str]]) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(_warning("quality_runner.cache_design must be a table"))
        return {}
    value = cast(dict[str, Any], value)
    paths = value.get("paths")
    if paths is None:
        return {"paths": []}
    if not isinstance(paths, list):
        warnings.append(_warning("quality_runner.cache_design.paths must be a list of tables"))
        return {"paths": []}
    paths = cast(list[object], paths)

    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(paths):
        field = f"quality_runner.cache_design.paths[{index}]"
        if not isinstance(item, dict):
            warnings.append(_warning(f"{field} must be a table"))
            continue
        item = cast(dict[str, Any], item)
        path = item.get("path")
        storage_class = item.get("class")
        lifecycle = item.get("lifecycle")
        reason = item.get("reason")
        if not _literal_relative_path(path):
            warnings.append(_warning(f"{field}.path must be a literal repository-relative path"))
            continue
        assert isinstance(path, str)
        normalized = PurePosixPath(path).as_posix().removeprefix("./")
        if normalized in seen:
            warnings.append(_warning(f"{field}.path duplicates {normalized}"))
            continue
        if storage_class not in CACHE_DESIGN_CLASSES:
            warnings.append(
                _warning(f"{field}.class must be one of {sorted(CACHE_DESIGN_CLASSES)}")
            )
            continue
        if lifecycle not in CACHE_DESIGN_LIFECYCLES:
            warnings.append(
                _warning(f"{field}.lifecycle must be one of {sorted(CACHE_DESIGN_LIFECYCLES)}")
            )
            continue
        bounds: dict[str, int] = {}
        invalid_bound = False
        for bound in _BOUND_FIELDS:
            raw = item.get(bound)
            if raw is None:
                continue
            if not isinstance(raw, int) or isinstance(raw, bool) or raw <= 0:
                warnings.append(_warning(f"{field}.{bound} must be a positive integer"))
                invalid_bound = True
            else:
                bounds[bound] = raw
        if invalid_bound:
            continue
        if lifecycle == "bounded" and not bounds:
            warnings.append(
                _warning(f"{field} uses bounded lifecycle but declares no lifecycle bound")
            )
            continue
        if lifecycle == "durable" and storage_class != "durable_state":
            warnings.append(
                _warning(f"{field} may use durable lifecycle only with class durable_state")
            )
            continue
        if storage_class == "durable_state" and lifecycle != "durable":
            warnings.append(_warning(f"{field} must use lifecycle durable for class durable_state"))
            continue
        if (
            storage_class == "durable_state"
            and normalized in _KNOWN_DISPOSABLE_PATHS
            and (not isinstance(reason, str) or not reason.strip())
        ):
            warnings.append(
                _warning(
                    f"{field}.reason is required when a known disposable path is "
                    "overridden as durable_state"
                )
            )
            continue
        parsed.append(
            {
                "path": normalized,
                "class": storage_class,
                "lifecycle": lifecycle,
                **bounds,
                **(
                    {"reason": reason.strip()} if isinstance(reason, str) and reason.strip() else {}
                ),
            }
        )
        seen.add(normalized)
    return {"paths": parsed}


def _literal_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        return False
    if any(character in value for character in "*?[]{}"):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() not in {".", ""}


def _warning(message: str) -> dict[str, str]:
    return {
        "code": "invalid_quality_runner_config_field",
        "message": message,
        "path": ".quality-runner.toml",
    }
