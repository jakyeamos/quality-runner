from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.artifacts import write_json
from quality_runner.exclusion_preflight import (
    build_run_only_overlay,
    exclusion_patterns_for_paths,
)
from quality_runner.scan_exclusions import (
    ScanExclusionOverlay,
    scan_exclusion_overlay_parts,
)


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


def config_with_scan_exclusion_overrides(
    config: dict[str, Any],
    scan_exclusion_overlay: ScanExclusionOverlay | None,
) -> dict[str, Any]:
    global_paths, module_paths = scan_exclusion_overlay_parts(scan_exclusion_overlay)
    global_patterns = exclusion_patterns_for_paths(global_paths)
    module_patterns = {
        module: exclusion_patterns_for_paths(paths) for module, paths in module_paths.items()
    }
    module_patterns = {module: patterns for module, patterns in module_patterns.items() if patterns}
    if not global_patterns and not module_patterns:
        return config

    merged = dict(config)
    existing = merged.get("scan_exclusions")
    exclusions = (
        [item for item in existing if isinstance(item, str)] if isinstance(existing, list) else []
    )
    for pattern in global_patterns:
        if pattern not in exclusions:
            exclusions.append(pattern)
    if global_patterns:
        merged["scan_exclusions"] = exclusions

    existing_by_module = merged.get("scan_exclusions_by_module")
    exclusions_by_module: dict[str, list[str]] = {}
    if isinstance(existing_by_module, dict):
        for module, patterns in existing_by_module.items():
            if isinstance(module, str) and isinstance(patterns, list):
                exclusions_by_module[module] = [item for item in patterns if isinstance(item, str)]
    for module, patterns in module_patterns.items():
        existing_patterns = exclusions_by_module.setdefault(module, [])
        for pattern in patterns:
            if pattern not in existing_patterns:
                existing_patterns.append(pattern)
    if module_patterns:
        merged["scan_exclusions_by_module"] = exclusions_by_module
    return merged


def apply_run_only_scan_exclusion(
    repo_root: Path,
    scan_exclusion_overlay: ScanExclusionOverlay | None,
    *,
    config: dict[str, Any],
    scan: dict[str, Any],
) -> dict[str, Any] | None:
    metadata = build_run_only_overlay(repo_root, scan_exclusion_overlay, config=config)
    if metadata is not None:
        scan["scan_exclusion_preflight"] = metadata
    return metadata


def add_scan_exclusion_artifact(
    artifact_paths: dict[str, str],
    run_dir: Path,
    metadata: dict[str, Any] | None,
) -> None:
    if metadata is not None:
        artifact_paths["scan_exclusion_overlay_json"] = str(
            write_json(run_dir / "scan-exclusion-overlay.json", metadata)
        )


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
