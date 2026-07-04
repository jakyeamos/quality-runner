from __future__ import annotations

from typing import Any


def config_with_include_overrides(
    config: dict[str, Any],
    include_ignored_paths: list[str] | None,
) -> dict[str, Any]:
    if not include_ignored_paths:
        return config
    merged = dict(config)
    structural_scan = dict(merged.get("structural_scan") or {})
    existing = structural_scan.get("include_ignored_paths")
    paths = (
        [item for item in existing if isinstance(item, str)] if isinstance(existing, list) else []
    )
    for path in include_ignored_paths:
        if path not in paths:
            paths.append(path)
    structural_scan["include_ignored_paths"] = paths
    merged["structural_scan"] = structural_scan
    return merged


def combined_warnings(scan: dict[str, Any], capability_map: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for source in (scan.get("warnings"), capability_map.get("warnings")):
        if not isinstance(source, list):
            continue
        for item in source:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "")
            message = str(item.get("message") or "")
            path = str(item.get("path") or "")
            key = (code, message, path)
            if key in seen:
                continue
            seen.add(key)
            warnings.append(item)
    return warnings


def gate_timeouts(config: dict[str, Any]) -> dict[str, int]:
    configured = config.get("gate_timeouts")
    if not isinstance(configured, dict):
        return {}
    return {
        gate_id: seconds
        for gate_id, seconds in configured.items()
        if isinstance(gate_id, str) and isinstance(seconds, int) and seconds > 0
    }
