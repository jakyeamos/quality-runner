from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from quality_runner.code_quality_duplicates import _duplicate_clusters, _extract_functions
from quality_runner.code_quality_findings import (
    CATEGORY_ORDER,
    _counts,
    _finding,
    _finding_sort_key,
)
from quality_runner.code_quality_ledger import (
    build_resolution_ledger,
    render_resolution_ledger_markdown,
)
from quality_runner.code_quality_paths import (
    IGNORED_DIRS,
    TEXT_EXTENSIONS,
    _check_coverage,
    _is_generated_file,
    _join_relative,
    _split_lines,
    _string_or_none,
    _under_generated_path,
    _verification_for_path,
)
from quality_runner.code_quality_rules import _scan_file
from quality_runner.schema_constants import CODE_QUALITY_SCAN_SCHEMA

__all__ = [
    "build_resolution_ledger",
    "create_code_quality_scan",
    "render_resolution_ledger_markdown",
]

DEFAULT_LARGE_FILE_LINES = 500
DEFAULT_FAT_ROUTER_LINES = 500


def create_code_quality_scan(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    policy = _structural_policy(config)
    disabled_groups = set(policy["disabled_rule_groups"])
    generated_paths = _generated_paths(scan)
    skipped_files: list[dict[str, str]] = []
    findings: list[dict[str, Any]] = []
    extracted_functions: list[dict[str, Any]] = []
    accountability: list[dict[str, Any]] = []

    for path in _discover_text_files(root, skipped_files, generated_paths):
        relative_path = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = _split_lines(text)
        accountability.append(
            {
                "path": relative_path,
                "line_count": len(lines),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "scan_status": "scanned",
                "check_coverage": _check_coverage(relative_path),
            }
        )
        findings.extend(
            _scan_file(
                relative_path=relative_path,
                text=text,
                lines=lines,
                disabled_groups=disabled_groups,
                large_file_lines=policy["large_file_lines"],
                fat_router_lines=policy["fat_router_lines"],
            )
        )
        extracted_functions.extend(_extract_functions(relative_path, lines))

    if "deduplicate" not in disabled_groups:
        duplicate_clusters = _duplicate_clusters(extracted_functions)
        for cluster in duplicate_clusters:
            first = cluster["candidates"][0]
            findings.append(
                _finding(
                    category="deduplicate",
                    severity="warning",
                    confidence="medium",
                    file=first["file"],
                    line=first["line"],
                    rule_id="near-duplicate-function",
                    evidence=f"{cluster['id']} spans {len(cluster['candidates'])} functions.",
                    expected_improvement=(
                        "Extract a shared helper only when the call sites share domain semantics."
                    ),
                    risk="Near-duplicate logic can drift across fixes.",
                    verification=_verification_for_path(first["file"]),
                    remediation_bucket="duplicate consolidation and helper extraction",
                )
            )
    else:
        duplicate_clusters = []

    sorted_findings = sorted(findings, key=_finding_sort_key)
    for index, finding in enumerate(sorted_findings, start=1):
        finding["id"] = f"CQ-{index:04d}"

    return {
        "schema": CODE_QUALITY_SCAN_SCHEMA,
        "run_id": _string_or_none(scan.get("run_id")),
        "repo_root": str(root),
        "summary": {
            "total_files": len(accountability),
            "total_lines": sum(item["line_count"] for item in accountability),
            "total_findings": len(sorted_findings),
            "findings_by_category": _counts(sorted_findings, "category", CATEGORY_ORDER),
            "findings_by_severity": _counts(
                sorted_findings, "severity", ["warning", "observation"]
            ),
            "duplicate_clusters": len(duplicate_clusters),
        },
        "accountability": accountability,
        "findings": sorted_findings,
        "duplicate_clusters": duplicate_clusters,
        "skipped_files": sorted(skipped_files, key=lambda item: item["path"]),
    }


def _structural_policy(config: dict[str, Any]) -> dict[str, Any]:
    policy = config.get("structural_scan")
    if not isinstance(policy, dict):
        policy = {}
    disabled = policy.get("disabled_rule_groups")
    large_file_lines = policy.get("large_file_lines")
    fat_router_lines = policy.get("fat_router_lines")
    return {
        "disabled_rule_groups": [item for item in disabled if isinstance(item, str)]
        if isinstance(disabled, list)
        else [],
        "large_file_lines": large_file_lines
        if isinstance(large_file_lines, int) and large_file_lines > 0
        else DEFAULT_LARGE_FILE_LINES,
        "fat_router_lines": fat_router_lines
        if isinstance(fat_router_lines, int) and fat_router_lines > 0
        else DEFAULT_FAT_ROUTER_LINES,
    }


def _discover_text_files(
    root: Path,
    skipped_files: list[dict[str, str]],
    generated_paths: set[str],
) -> list[Path]:
    files: list[Path] = []
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        relative_current = current_path.relative_to(root).as_posix()
        ignored = sorted(
            name
            for name in dir_names
            if name in IGNORED_DIRS
            or _under_generated_path(_join_relative(relative_current, name), generated_paths)
        )
        for name in ignored:
            skipped_files.append(
                {
                    "path": (current_path / name).relative_to(root).as_posix(),
                    "reason": "generated directory"
                    if _under_generated_path(
                        _join_relative(relative_current, name), generated_paths
                    )
                    else "ignored directory",
                }
            )
        dir_names[:] = sorted(
            name
            for name in dir_names
            if name not in IGNORED_DIRS
            and not _under_generated_path(_join_relative(relative_current, name), generated_paths)
        )
        for file_name in sorted(file_names):
            path = current_path / file_name
            relative_path = path.relative_to(root).as_posix()
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            if _is_generated_file(relative_path):
                skipped_files.append({"path": relative_path, "reason": "generated file"})
                continue
            if path.suffix in TEXT_EXTENSIONS or path.name in {"Dockerfile", "Makefile"}:
                files.append(path)
    return files


def _generated_paths(scan: dict[str, Any]) -> set[str]:
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
