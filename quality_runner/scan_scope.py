from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from quality_runner.code_quality_paths import (
    _artifact_directory_reason,
    _ignored_directory_reason,
    _is_generated_file,
    _join_relative,
    _top_level_ignored_directory_reason,
    _under_generated_path,
)
from quality_runner.core.audit_contracts import AuditPayload, ScannedTextFile, TextScanScope
from quality_runner.scan_exclusions import (
    record_scan_activity,
)
from quality_runner.scan_scope_helpers import (
    _scope_allows_directory,
    _scope_includes_file,
    effective_scan_exclusions,
    generated_paths,
    is_scan_excluded,
    is_security_surface_file,
    is_text_file,
    normalized_path_list,
)
from quality_runner.scan_scope_reading import read_text_file
from quality_runner.scan_scope_reporting import (
    estimate_text_files,
    estimated_scan_seconds,
    scan_budget_summary,
    skipped_directory_entry,
    skipped_path_summary,
)
from quality_runner.scan_scope_reporting import (
    fast_skipped_directory_entry as _fast_skipped_directory_entry,
)
from quality_runner.semantic_similarity_policy import similarity_policy_defaults
from quality_runner.source_analysis_cache import SourceAnalysisCache

DEFAULT_LARGE_FILE_LINES = 500
DEFAULT_FAT_ROUTER_LINES = 500
DEFAULT_MAX_TEXT_FILES = 2_500
DEFAULT_MAX_SECURITY_SURFACE_PATHS = 5_000
__all__ = [
    "create_text_scan_scope",
    "discover_scan_inventory",
    "discover_security_surface_paths",
    "discover_text_files",
    "effective_scan_exclusions",
    "estimate_text_files",
    "estimated_scan_seconds",
    "generated_paths",
    "is_security_surface_file",
    "is_scan_excluded",
    "is_text_file",
    "scan_budget_summary",
    "skipped_directory_entry",
    "skipped_path_summary",
    "structural_scan_policy",
]


def structural_scan_policy(config: dict[str, Any]) -> dict[str, Any]:
    policy = config.get("structural_scan")
    if not isinstance(policy, dict):
        policy = {}
    disabled = policy.get("disabled_rule_groups")
    large_file_lines = policy.get("large_file_lines")
    fat_router_lines = policy.get("fat_router_lines")
    max_text_files = policy.get("max_text_files")
    similarity_enabled = policy.get("similarity_enabled")
    similarity_backend = policy.get("similarity_backend")
    similarity_threshold = policy.get("similarity_threshold")
    similarity_min_lines = policy.get("similarity_min_lines")
    similarity_max_pairs = policy.get("similarity_max_pairs")
    similarity_timeout_seconds = policy.get("similarity_timeout_seconds")
    similarity_include_tests = policy.get("similarity_include_tests")
    resolved = {
        "disabled_rule_groups": [item for item in disabled if isinstance(item, str)]
        if isinstance(disabled, list)
        else [],
        "include_ignored_paths": normalized_path_list(policy.get("include_ignored_paths")),
        "large_file_lines": large_file_lines
        if isinstance(large_file_lines, int) and large_file_lines > 0
        else DEFAULT_LARGE_FILE_LINES,
        "fat_router_lines": fat_router_lines
        if isinstance(fat_router_lines, int) and fat_router_lines > 0
        else DEFAULT_FAT_ROUTER_LINES,
        "max_text_files": max_text_files
        if isinstance(max_text_files, int) and max_text_files > 0
        else DEFAULT_MAX_TEXT_FILES,
        "similarity_enabled": similarity_enabled,
        "similarity_backend": similarity_backend,
        "similarity_threshold": similarity_threshold,
        "similarity_min_lines": similarity_min_lines,
        "similarity_max_pairs": similarity_max_pairs,
        "similarity_timeout_seconds": similarity_timeout_seconds,
        "similarity_include_tests": similarity_include_tests,
    }
    return {**resolved, **similarity_policy_defaults(resolved)}


def create_text_scan_scope(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
    module: str | None = None,
    focus_paths: tuple[str, ...] = (),
    read_files: bool = True,
    cache_mode: str = "repo",
    cache_root: Path | None = None,
    include_paths: tuple[str, ...] = (),
) -> TextScanScope:
    root = repo_root.expanduser().resolve()
    policy = structural_scan_policy(config)
    scan_inclusions = _unique_paths([*policy["include_ignored_paths"], *include_paths])
    scan_exclusions = effective_scan_exclusions(root, config, module=module)
    inventory = discover_scan_inventory(
        root,
        generated_paths=generated_paths(scan),
        include_ignored_paths=set(scan_inclusions),
        scan_exclusions=scan_exclusions,
        max_text_files=policy["max_text_files"],
        focus_paths=focus_paths,
        include_paths=include_paths,
    )
    paths = inventory["text_paths"]
    skipped_files = list(inventory["skipped_files"])
    if read_files:
        skipped_files = _materialize_skipped_estimates(root, skipped_files)
    security_surface_paths = inventory["security_surface_paths"]
    files: list[ScannedTextFile] = []
    bytes_read = 0
    if read_files:
        for path in paths:
            file_info = read_text_file(root, path)
            files.append(file_info)
            bytes_read += len(file_info.text.encode("utf-8"))
    inventory_payload = dict(inventory["metrics"])
    inventory_payload["bytes_read"] = bytes_read
    inventory_payload["text_paths"] = len(paths)
    inventory_payload["security_surface_paths"] = len(security_surface_paths)
    return TextScanScope(
        repo_root=root,
        files=tuple(files),
        skipped_files=tuple(skipped_files),
        max_text_files=policy["max_text_files"],
        scan_exclusions=tuple(scan_exclusions),
        security_surface_paths=tuple(security_surface_paths),
        source_analysis_cache=SourceAnalysisCache(
            root,
            cache_mode=cache_mode,
            cache_root=cache_root,
        ),
        focus_paths=tuple(sorted(set(focus_paths))),
        file_paths=tuple(path.relative_to(root).as_posix() for path in paths),
        inventory=inventory_payload,
        include_paths=include_paths,
        scan_inclusions=tuple(scan_inclusions),
    )


def discover_scan_inventory(
    root: Path,
    *,
    generated_paths: set[str],
    include_ignored_paths: set[str],
    scan_exclusions: list[str],
    max_text_files: int,
    focus_paths: tuple[str, ...] = (),
    include_paths: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Walk the repository once and produce both analysis and security scope inputs."""
    include_ignored_paths = set(include_ignored_paths) | set(include_paths)
    text_paths: list[Path] = []
    security_surface_paths: list[str] = []
    skipped_files: list[AuditPayload] = []
    metrics: dict[str, int] = {
        "visited_directories": 0,
        "visited_files": 0,
        "visited_paths": 0,
        "skipped_paths": 0,
        "text_candidates": 0,
    }
    scan_budget_exceeded = False

    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        metrics["visited_directories"] += 1
        metrics["visited_paths"] += 1
        relative_current = current_path.relative_to(root).as_posix()
        if include_paths and not _scope_allows_directory(relative_current, include_paths):
            dir_names[:] = []
            continue
        ignored: list[tuple[str, str]] = []
        for name in sorted(dir_names):
            relative_name = _join_relative(relative_current, name)
            generated = _under_generated_path(relative_name, generated_paths)
            preferred_reason = _artifact_directory_reason(
                relative_name, include_ignored_paths=include_ignored_paths
            ) or _top_level_ignored_directory_reason(
                relative_name, include_ignored_paths=include_ignored_paths
            )
            reason = (
                "generated directory"
                if generated
                else preferred_reason
                if preferred_reason is not None
                else "scan exclusion"
                if is_scan_excluded(
                    relative_name,
                    scan_exclusions=scan_exclusions,
                    include_ignored_paths=include_ignored_paths,
                )
                else _ignored_directory_reason(
                    relative_name, include_ignored_paths=include_ignored_paths
                )
            )
            if reason is not None:
                ignored.append((name, reason))
        for directory_name, reason in ignored:
            skipped_files.append(
                _fast_skipped_directory_entry(root, current_path / directory_name, reason)
            )
        metrics["skipped_paths"] += len(ignored)
        ignored_names = {name for name, _reason in ignored}
        dir_names[:] = sorted(name for name in dir_names if name not in ignored_names)

        for file_name in sorted(file_names):
            metrics["visited_files"] += 1
            metrics["visited_paths"] += 1
            path = current_path / file_name
            relative_path = path.relative_to(root).as_posix()
            if include_paths and not _scope_includes_file(relative_path, include_paths):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if is_scan_excluded(
                relative_path,
                scan_exclusions=scan_exclusions,
                include_ignored_paths=include_ignored_paths,
            ):
                if is_text_file(path):
                    skipped_files.append({"path": relative_path, "reason": "scan exclusion"})
                    metrics["skipped_paths"] += 1
                continue
            if _is_generated_file(relative_path):
                skipped_files.append({"path": relative_path, "reason": "generated file"})
                metrics["skipped_paths"] += 1
                continue
            if (
                is_security_surface_file(path, relative_path)
                and len(security_surface_paths) < DEFAULT_MAX_SECURITY_SURFACE_PATHS
            ):
                security_surface_paths.append(relative_path)
            if not is_text_file(path):
                continue
            metrics["text_candidates"] += 1
            if focus_paths and not _path_in_focus(relative_path, focus_paths):
                continue
            if scan_budget_exceeded or len(text_paths) >= max_text_files:
                scan_budget_exceeded = True
                skipped_files.append({"path": relative_path, "reason": "scan budget exceeded"})
                metrics["skipped_paths"] += 1
                continue
            text_paths.append(path)

    return {
        "text_paths": text_paths,
        "security_surface_paths": security_surface_paths,
        "skipped_files": skipped_files,
        "metrics": metrics,
    }


def _materialize_skipped_estimates(
    root: Path,
    skipped_files: list[AuditPayload],
) -> list[AuditPayload]:
    materialized: list[AuditPayload] = []
    for item in skipped_files:
        if item.get("estimate_deferred") is not True:
            materialized.append(item)
            continue
        relative_path = item.get("path")
        reason = item.get("reason")
        if not isinstance(relative_path, str) or not isinstance(reason, str):
            materialized.append(item)
            continue
        materialized.append(skipped_directory_entry(root, root / relative_path, reason))
    return materialized


def discover_text_files(
    root: Path,
    *,
    skipped_files: list[AuditPayload],
    generated_paths: set[str],
    include_ignored_paths: set[str],
    scan_exclusions: list[str],
    max_text_files: int,
    focus_paths: tuple[str, ...] = (),
    include_paths: tuple[str, ...] = (),
) -> list[Path]:
    include_ignored_paths = set(include_ignored_paths) | set(include_paths)
    files: list[Path] = []
    scan_budget_exceeded = False
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        record_scan_activity(root, current_path, kind="text-scan")
        relative_current = current_path.relative_to(root).as_posix()
        if include_paths and not _scope_allows_directory(relative_current, include_paths):
            dir_names[:] = []
            continue
        if scan_budget_exceeded:
            skipped_files.append(
                skipped_directory_entry(root, current_path, "scan budget exceeded")
            )
            dir_names[:] = []
            continue
        ignored: list[tuple[str, str]] = []
        for name in sorted(dir_names):
            relative_name = _join_relative(relative_current, name)
            generated = _under_generated_path(relative_name, generated_paths)
            preferred_reason = _artifact_directory_reason(
                relative_name, include_ignored_paths=include_ignored_paths
            ) or _top_level_ignored_directory_reason(
                relative_name, include_ignored_paths=include_ignored_paths
            )
            reason = (
                "generated directory"
                if generated
                else preferred_reason
                if preferred_reason is not None
                else "scan exclusion"
                if is_scan_excluded(
                    relative_name,
                    scan_exclusions=scan_exclusions,
                    include_ignored_paths=include_ignored_paths,
                )
                else _ignored_directory_reason(
                    relative_name, include_ignored_paths=include_ignored_paths
                )
            )
            if reason is not None:
                ignored.append((name, reason))
        for directory_name, reason in ignored:
            skipped_files.append(
                skipped_directory_entry(root, current_path / directory_name, reason)
            )
        ignored_names = {name for name, _reason in ignored}
        dir_names[:] = sorted(name for name in dir_names if name not in ignored_names)
        for file_name in sorted(file_names):
            path = current_path / file_name
            relative_path = path.relative_to(root).as_posix()
            if include_paths and not _scope_includes_file(relative_path, include_paths):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if is_scan_excluded(
                relative_path,
                scan_exclusions=scan_exclusions,
                include_ignored_paths=include_ignored_paths,
            ):
                if is_text_file(path):
                    skipped_files.append({"path": relative_path, "reason": "scan exclusion"})
                continue
            if _is_generated_file(relative_path):
                skipped_files.append({"path": relative_path, "reason": "generated file"})
                continue
            if focus_paths and not _path_in_focus(relative_path, focus_paths):
                continue
            if is_text_file(path):
                if len(files) >= max_text_files:
                    skipped_files.append({"path": relative_path, "reason": "scan budget exceeded"})
                    scan_budget_exceeded = True
                    continue
                files.append(path)
        if scan_budget_exceeded:
            for directory_name in dir_names:
                skipped_files.append(
                    skipped_directory_entry(
                        root,
                        current_path / directory_name,
                        "scan budget exceeded",
                    )
                )
            dir_names[:] = []
    return files


def discover_security_surface_paths(
    root: Path,
    *,
    generated_paths: set[str],
    include_ignored_paths: set[str],
    scan_exclusions: list[str],
    focus_paths: tuple[str, ...] = (),
    include_paths: tuple[str, ...] = (),
) -> list[str]:
    include_ignored_paths = set(include_ignored_paths) | set(include_paths)
    surface_paths: list[str] = []
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        record_scan_activity(root, current_path, kind="text-scan")
        relative_current = current_path.relative_to(root).as_posix()
        if include_paths and not _scope_allows_directory(relative_current, include_paths):
            dir_names[:] = []
            continue
        ignored_names: set[str] = set()
        for name in sorted(dir_names):
            relative_name = _join_relative(relative_current, name)
            generated = _under_generated_path(relative_name, generated_paths)
            preferred_reason = _artifact_directory_reason(
                relative_name, include_ignored_paths=include_ignored_paths
            ) or _top_level_ignored_directory_reason(
                relative_name, include_ignored_paths=include_ignored_paths
            )
            reason = (
                "generated directory"
                if generated
                else preferred_reason
                if preferred_reason is not None
                else "scan exclusion"
                if is_scan_excluded(
                    relative_name,
                    scan_exclusions=scan_exclusions,
                    include_ignored_paths=include_ignored_paths,
                )
                else _ignored_directory_reason(
                    relative_name, include_ignored_paths=include_ignored_paths
                )
            )
            if reason is not None:
                ignored_names.add(name)
        dir_names[:] = sorted(name for name in dir_names if name not in ignored_names)
        for file_name in sorted(file_names):
            path = current_path / file_name
            relative_path = path.relative_to(root).as_posix()
            if include_paths and not _scope_includes_file(relative_path, include_paths):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            if is_scan_excluded(
                relative_path,
                scan_exclusions=scan_exclusions,
                include_ignored_paths=include_ignored_paths,
            ) or _is_generated_file(relative_path):
                continue
            if not is_security_surface_file(path, relative_path):
                continue
            if focus_paths and not _path_in_focus(relative_path, focus_paths):
                continue
            surface_paths.append(relative_path)
            if len(surface_paths) >= DEFAULT_MAX_SECURITY_SURFACE_PATHS:
                return surface_paths
    return surface_paths


def _path_in_focus(relative_path: str, focus_paths: tuple[str, ...]) -> bool:
    normalized = relative_path.strip("/")
    return any(
        normalized == focus or normalized.startswith(f"{focus}/")
        for focus in (item.strip("/") for item in focus_paths)
        if focus
    )


def _unique_paths(values: list[object]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().strip("/")
        if not normalized or normalized in seen:
            continue
        paths.append(normalized)
        seen.add(normalized)
    return paths
