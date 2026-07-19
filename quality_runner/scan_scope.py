from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Any

from quality_runner.code_quality_paths import (
    TEXT_EXTENSIONS,
    _artifact_directory_reason,
    _ignored_directory_reason,
    _is_generated_file,
    _is_included_or_included_parent,
    _join_relative,
    _split_lines,
    _top_level_ignored_directory_reason,
    _under_generated_path,
)
from quality_runner.core.audit_contracts import AuditPayload, ScannedTextFile, TextScanScope
from quality_runner.scan_exclusions import (
    ALWAYS_EXCLUDED_PATH_PARTS,
    matches_scan_exclusion,
    record_scan_activity,
)
from quality_runner.scan_exclusions import (
    effective_scan_exclusions as configured_effective_scan_exclusions,
)
from quality_runner.security_surface_paths import is_security_surface_path
from quality_runner.semantic_similarity_policy import similarity_policy_defaults

DEFAULT_LARGE_FILE_LINES = 500
DEFAULT_FAT_ROUTER_LINES = 500
DEFAULT_SKIPPED_PATH_ESTIMATE_LIMIT = 10_000
DEFAULT_MAX_TEXT_FILES = 2_500
DEFAULT_MAX_SECURITY_SURFACE_PATHS = 5_000
ESTIMATED_SCAN_SECONDS_PER_TEXT_FILE = 0.015
NON_RECURSIVE_SKIPPED_DIRECTORY_REASONS = frozenset(
    {"artifact directory", "generated directory", "scan exclusion"}
)
TEXT_FILE_NAMES = {"Dockerfile", "Makefile"}
SECURITY_SURFACE_FILE_NAMES = {"Cargo.toml", "go.mod", "package.json", "pyproject.toml"}


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
) -> TextScanScope:
    root = repo_root.expanduser().resolve()
    policy = structural_scan_policy(config)
    skipped_files: list[AuditPayload] = []
    scan_exclusions = effective_scan_exclusions(root, config, module=module)
    paths = discover_text_files(
        root,
        skipped_files=skipped_files,
        generated_paths=generated_paths(scan),
        include_ignored_paths=set(policy["include_ignored_paths"]),
        scan_exclusions=scan_exclusions,
        max_text_files=policy["max_text_files"],
    )
    security_surface_paths = discover_security_surface_paths(
        root,
        generated_paths=generated_paths(scan),
        include_ignored_paths=set(policy["include_ignored_paths"]),
        scan_exclusions=scan_exclusions,
    )
    files = tuple(_read_text_file(root, path) for path in paths)
    return TextScanScope(
        repo_root=root,
        files=files,
        skipped_files=tuple(skipped_files),
        max_text_files=policy["max_text_files"],
        scan_exclusions=tuple(scan_exclusions),
        security_surface_paths=tuple(security_surface_paths),
    )


def discover_text_files(
    root: Path,
    *,
    skipped_files: list[AuditPayload],
    generated_paths: set[str],
    include_ignored_paths: set[str],
    scan_exclusions: list[str],
    max_text_files: int,
) -> list[Path]:
    files: list[Path] = []
    scan_budget_exceeded = False
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        record_scan_activity(root, current_path, kind="text-scan")
        relative_current = current_path.relative_to(root).as_posix()
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
) -> list[str]:
    surface_paths: list[str] = []
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        record_scan_activity(root, current_path, kind="text-scan")
        relative_current = current_path.relative_to(root).as_posix()
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
            surface_paths.append(relative_path)
            if len(surface_paths) >= DEFAULT_MAX_SECURITY_SURFACE_PATHS:
                return surface_paths
    return surface_paths


def generated_paths(scan: dict[str, Any]) -> set[str]:
    generated_code = scan.get("generated_code")
    if not isinstance(generated_code, list):
        return set()
    paths: set[str] = set()
    for item in generated_code:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if isinstance(path, str) and path:
            paths.add(path.strip("/"))
    return paths


def is_text_file(path: Path) -> bool:
    return path.suffix in TEXT_EXTENSIONS or path.name in TEXT_FILE_NAMES


def is_security_surface_file(path: Path, relative_path: str) -> bool:
    return path.name in SECURITY_SURFACE_FILE_NAMES or is_security_surface_path(relative_path)


def effective_scan_exclusions(
    root: Path,
    config: dict[str, Any],
    *,
    module: str | None = None,
) -> list[str]:
    return configured_effective_scan_exclusions(root, config, module=module)


def skipped_directory_entry(root: Path, path: Path, reason: str) -> AuditPayload:
    relative_path = path.relative_to(root).as_posix()
    if should_estimate_skipped_directory(relative_path, reason):
        record_scan_activity(root, path, kind="excluded-directory-estimation")
        estimated_files, estimate_truncated = estimate_text_files(path)
        estimate_status = "estimated"
        estimate_reason = "recursive text-file count"
    else:
        estimated_files = 0
        estimate_truncated = False
        estimate_status = "not-estimated"
        estimate_reason = "protected or excluded artifact directory"
    return {
        "path": relative_path,
        "reason": reason,
        "estimated_text_files": estimated_files,
        "estimated_scan_seconds": estimated_scan_seconds(estimated_files),
        "estimate_truncated": estimate_truncated,
        "estimate_status": estimate_status,
        "estimate_reason": estimate_reason,
        "include_config_hint": (
            f'[quality_runner.structural_scan] include_ignored_paths = ["{relative_path}"]'
        ),
    }


def should_estimate_skipped_directory(relative_path: str, reason: str) -> bool:
    path_parts = PurePosixPath(relative_path).parts
    if any(part in ALWAYS_EXCLUDED_PATH_PARTS for part in path_parts):
        return False
    return reason not in NON_RECURSIVE_SKIPPED_DIRECTORY_REASONS


def is_scan_excluded(
    relative_path: str,
    *,
    scan_exclusions: list[str],
    include_ignored_paths: set[str],
) -> bool:
    normalized = relative_path.strip("/")
    return bool(
        normalized
        and not _is_included_or_included_parent(normalized, include_ignored_paths)
        and matches_scan_exclusion(normalized, scan_exclusions)
    )


def scan_budget_summary(
    *,
    scanned_files: int,
    max_text_files: int,
    skipped_files: list[AuditPayload],
) -> AuditPayload:
    skipped_by_budget = [
        item for item in skipped_files if item.get("reason") == "scan budget exceeded"
    ]
    return {
        "max_text_files": max_text_files,
        "scanned_text_files": scanned_files,
        "budget_exceeded": bool(skipped_by_budget),
        "skipped_text_files": len(skipped_by_budget),
    }


def skipped_path_summary(skipped_files: list[AuditPayload]) -> AuditPayload:
    estimated_files = 0
    estimated_directories = 0
    unestimated_directories = 0
    for item in skipped_files:
        value = item.get("estimated_text_files")
        if isinstance(value, int):
            estimated_files += value
        estimate_status = item.get("estimate_status")
        if estimate_status == "estimated":
            estimated_directories += 1
        elif estimate_status == "not-estimated":
            unestimated_directories += 1
    directory_estimate_status = (
        "none"
        if not estimated_directories and not unestimated_directories
        else "partial"
        if unestimated_directories
        else "complete"
    )
    return {
        "skipped_paths": len(skipped_files),
        "skipped_estimated_text_files": estimated_files,
        "skipped_estimated_scan_seconds": estimated_scan_seconds(estimated_files),
        "skipped_estimate_truncated": any(
            item.get("estimate_truncated") is True for item in skipped_files
        ),
        "skipped_estimated_directories": estimated_directories,
        "skipped_unestimated_directories": unestimated_directories,
        "skipped_directory_estimate_status": directory_estimate_status,
    }


def normalized_path_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    paths: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            continue
        paths.append(item.strip("/"))
    return paths


def estimate_text_files(path: Path) -> tuple[int, bool]:
    if not path.is_dir():
        return 0, False

    count = 0
    for current_root, dir_names, file_names in os.walk(path):
        dir_names[:] = sorted(
            name for name in dir_names if not (Path(current_root) / name).is_symlink()
        )
        for file_name in sorted(file_names):
            file_path = Path(current_root) / file_name
            if file_path.is_symlink() or not file_path.is_file():
                continue
            if is_text_file(file_path):
                count += 1
                if count >= DEFAULT_SKIPPED_PATH_ESTIMATE_LIMIT:
                    return count, True
    return count, False


def estimated_scan_seconds(estimated_files: int) -> float:
    if estimated_files <= 0:
        return 0.0
    return max(0.1, round(estimated_files * ESTIMATED_SCAN_SECONDS_PER_TEXT_FILE, 1))


def _read_text_file(root: Path, path: Path) -> ScannedTextFile:
    text = path.read_text(encoding="utf-8", errors="replace")
    return ScannedTextFile(
        path=path.relative_to(root).as_posix(),
        text=text,
        lines=_split_lines(text),
    )
