from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.code_quality_paths import (
    TEXT_EXTENSIONS,
    _is_included_or_included_parent,
)
from quality_runner.scan_exclusions import (
    effective_scan_exclusions as configured_effective_scan_exclusions,
)
from quality_runner.scan_exclusions import (
    matches_scan_exclusion,
)
from quality_runner.security_surface_paths import is_security_surface_path

TEXT_FILE_NAMES = {"Dockerfile", "Makefile"}
SECURITY_SURFACE_FILE_NAMES = {"Cargo.toml", "go.mod", "package.json", "pyproject.toml"}


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


def _scope_allows_directory(path: str, include_paths: tuple[str, ...]) -> bool:
    normalized = path.strip("/")
    if normalized == ".":
        normalized = ""
    return not normalized or any(
        item == normalized
        or item.startswith(f"{normalized}/")
        or normalized.startswith(f"{item}/")
        for item in include_paths
    )


def _scope_includes_file(path: str, include_paths: tuple[str, ...]) -> bool:
    normalized = path.strip("/")
    return any(normalized == item or normalized.startswith(f"{item}/") for item in include_paths)


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


def normalized_path_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    paths: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            continue
        paths.append(item.strip("/"))
    return paths
