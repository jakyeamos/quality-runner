from __future__ import annotations

import gzip
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
    TEXT_EXTENSIONS,
    _artifact_directory_reason,
    _check_coverage,
    _ignored_directory_reason,
    _is_generated_file,
    _is_included_or_included_parent,
    _join_relative,
    _split_lines,
    _string_or_none,
    _top_level_ignored_directory_reason,
    _under_generated_path,
    _verification_for_path,
)
from quality_runner.code_quality_ponytail import ponytail_findings
from quality_runner.code_quality_rules import _scan_file
from quality_runner.scan_exclusions import (
    gitignore_scan_exclusions,
    matches_scan_exclusion,
    resolve_scan_exclusions,
)
from quality_runner.schema_constants import CODE_QUALITY_SCAN_SCHEMA

__all__ = [
    "build_resolution_ledger",
    "create_code_quality_scan",
    "preview_ignored_paths",
    "render_resolution_ledger_markdown",
]

DEFAULT_LARGE_FILE_LINES = 500
DEFAULT_FAT_ROUTER_LINES = 500
DEFAULT_GZIPPED_JS_BUNDLE_BYTES = 200_000
DEFAULT_SKIPPED_PATH_ESTIMATE_LIMIT = 10_000
DEFAULT_MAX_TEXT_FILES = 2_500
ESTIMATED_SCAN_SECONDS_PER_TEXT_FILE = 0.015
JS_BUNDLE_DIRS = (
    ".next/static/chunks",
    "build/static/js",
    "dist/assets",
    "out/_next/static/chunks",
)


def create_code_quality_scan(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    policy = _structural_policy(config)
    disabled_groups = set(policy["disabled_rule_groups"])
    include_ignored_paths = set(policy["include_ignored_paths"])
    scan_exclusions = _effective_scan_exclusions(root, config)
    generated_paths = _generated_paths(scan)
    skipped_files: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    extracted_functions: list[dict[str, Any]] = []
    accountability: list[dict[str, Any]] = []
    scanned_files: list[dict[str, Any]] = []

    for path in _discover_text_files(
        root,
        skipped_files,
        generated_paths,
        include_ignored_paths,
        scan_exclusions,
        policy["max_text_files"],
    ):
        relative_path = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = _split_lines(text)
        scanned_files.append({"path": relative_path, "text": text, "lines": lines})
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

    if "ponytail" not in disabled_groups:
        findings.extend(ponytail_findings(scanned_files))

    if "speed" not in disabled_groups:
        findings.extend(_bundle_budget_findings(root))

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
            "scan_budget": _scan_budget_summary(
                scanned_files=len(accountability),
                max_text_files=policy["max_text_files"],
                skipped_files=skipped_files,
            ),
            **_skipped_path_summary(skipped_files),
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
    max_text_files = policy.get("max_text_files")
    return {
        "disabled_rule_groups": [item for item in disabled if isinstance(item, str)]
        if isinstance(disabled, list)
        else [],
        "include_ignored_paths": _normalized_path_list(policy.get("include_ignored_paths")),
        "large_file_lines": large_file_lines
        if isinstance(large_file_lines, int) and large_file_lines > 0
        else DEFAULT_LARGE_FILE_LINES,
        "fat_router_lines": fat_router_lines
        if isinstance(fat_router_lines, int) and fat_router_lines > 0
        else DEFAULT_FAT_ROUTER_LINES,
        "max_text_files": max_text_files
        if isinstance(max_text_files, int) and max_text_files > 0
        else DEFAULT_MAX_TEXT_FILES,
    }


def _discover_text_files(
    root: Path,
    skipped_files: list[dict[str, Any]],
    generated_paths: set[str],
    include_ignored_paths: set[str],
    scan_exclusions: list[str],
    max_text_files: int,
) -> list[Path]:
    files: list[Path] = []
    scan_budget_exceeded = False
    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        relative_current = current_path.relative_to(root).as_posix()
        if scan_budget_exceeded:
            skipped_files.append(
                _skipped_directory_entry(root, current_path, "scan budget exceeded")
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
                if _is_scan_excluded(
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
        for name in ignored:
            directory_name, reason = name
            skipped_files.append(
                _skipped_directory_entry(root, current_path / directory_name, reason)
            )
        ignored_names = {name for name, _reason in ignored}
        dir_names[:] = sorted(name for name in dir_names if name not in ignored_names)
        for file_name in sorted(file_names):
            path = current_path / file_name
            relative_path = path.relative_to(root).as_posix()
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            if _is_scan_excluded(
                relative_path,
                scan_exclusions=scan_exclusions,
                include_ignored_paths=include_ignored_paths,
            ):
                if path.suffix in TEXT_EXTENSIONS or path.name in {"Dockerfile", "Makefile"}:
                    skipped_files.append({"path": relative_path, "reason": "scan exclusion"})
                continue
            if _is_generated_file(relative_path):
                skipped_files.append({"path": relative_path, "reason": "generated file"})
                continue
            if path.suffix in TEXT_EXTENSIONS or path.name in {"Dockerfile", "Makefile"}:
                if len(files) >= max_text_files:
                    skipped_files.append({"path": relative_path, "reason": "scan budget exceeded"})
                    scan_budget_exceeded = True
                    continue
                files.append(path)
        if scan_budget_exceeded:
            for directory_name in dir_names:
                skipped_files.append(
                    _skipped_directory_entry(
                        root,
                        current_path / directory_name,
                        "scan budget exceeded",
                    )
                )
            dir_names[:] = []
    return files


def preview_ignored_paths(
    repo_root: Path,
    *,
    config: dict[str, Any],
    scan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    root = repo_root.expanduser().resolve()
    policy = _structural_policy(config)
    skipped_files: list[dict[str, Any]] = []
    _discover_text_files(
        root,
        skipped_files,
        _generated_paths(scan or {}),
        set(policy["include_ignored_paths"]),
        _effective_scan_exclusions(root, config),
        policy["max_text_files"],
    )
    return [
        item
        for item in sorted(skipped_files, key=lambda skipped: skipped["path"])
        if item.get("reason") == "ignored directory"
    ]


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


def _effective_scan_exclusions(root: Path, config: dict[str, Any]) -> list[str]:
    return [*resolve_scan_exclusions(config), *gitignore_scan_exclusions(root)]


def _skipped_directory_entry(root: Path, path: Path, reason: str) -> dict[str, Any]:
    relative_path = path.relative_to(root).as_posix()
    estimated_files, estimate_truncated = _estimate_text_files(path)
    return {
        "path": relative_path,
        "reason": reason,
        "estimated_text_files": estimated_files,
        "estimated_scan_seconds": _estimated_scan_seconds(estimated_files),
        "estimate_truncated": estimate_truncated,
        "include_config_hint": (
            f'[quality_runner.structural_scan] include_ignored_paths = ["{relative_path}"]'
        ),
    }


def _is_scan_excluded(
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


def _estimate_text_files(path: Path) -> tuple[int, bool]:
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
            if file_path.suffix in TEXT_EXTENSIONS or file_path.name in {"Dockerfile", "Makefile"}:
                count += 1
                if count >= DEFAULT_SKIPPED_PATH_ESTIMATE_LIMIT:
                    return count, True
    return count, False


def _estimated_scan_seconds(estimated_files: int) -> float:
    if estimated_files <= 0:
        return 0.0
    return max(0.1, round(estimated_files * ESTIMATED_SCAN_SECONDS_PER_TEXT_FILE, 1))


def _skipped_path_summary(skipped_files: list[dict[str, Any]]) -> dict[str, Any]:
    estimated_files = sum(
        item.get("estimated_text_files", 0)
        for item in skipped_files
        if isinstance(item.get("estimated_text_files"), int)
    )
    return {
        "skipped_paths": len(skipped_files),
        "skipped_estimated_text_files": estimated_files,
        "skipped_estimated_scan_seconds": _estimated_scan_seconds(estimated_files),
        "skipped_estimate_truncated": any(
            item.get("estimate_truncated") is True for item in skipped_files
        ),
    }


def _scan_budget_summary(
    *,
    scanned_files: int,
    max_text_files: int,
    skipped_files: list[dict[str, Any]],
) -> dict[str, Any]:
    skipped_by_budget = [
        item for item in skipped_files if item.get("reason") == "scan budget exceeded"
    ]
    return {
        "max_text_files": max_text_files,
        "scanned_text_files": scanned_files,
        "budget_exceeded": bool(skipped_by_budget),
        "skipped_text_files": len(skipped_by_budget),
    }


def _normalized_path_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    paths: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            continue
        paths.append(item.strip("/"))
    return paths


def _bundle_budget_findings(root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for bundle_dir in JS_BUNDLE_DIRS:
        path = root / bundle_dir
        if not path.is_dir():
            continue
        for bundle in sorted(path.rglob("*.js")):
            if bundle.name.endswith(".map") or not bundle.is_file():
                continue
            raw = bundle.read_bytes()
            gzipped_size = len(gzip.compress(raw))
            if gzipped_size <= DEFAULT_GZIPPED_JS_BUNDLE_BYTES:
                continue
            relative_path = bundle.relative_to(root).as_posix()
            findings.append(
                _finding(
                    category="speed",
                    severity="observation",
                    confidence="medium",
                    file=relative_path,
                    line=1,
                    rule_id="large-js-bundle-artifact",
                    evidence=f"{gzipped_size} gzipped bytes",
                    expected_improvement=(
                        "Split initial routes, lazy-load heavy features, or remove unused dependencies."
                    ),
                    risk="Large initial JavaScript bundles delay load and interaction readiness.",
                    verification="Run bundle analysis and the relevant frontend build.",
                    remediation_bucket="frontend performance and bundle budget",
                )
            )
    return findings
