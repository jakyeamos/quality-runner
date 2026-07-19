from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

from quality_runner.code_quality_architecture import architecture_findings
from quality_runner.code_quality_bundles import bundle_budget_findings
from quality_runner.code_quality_duplicates import _extract_functions
from quality_runner.code_quality_findings import (
    CATEGORY_ORDER,
    _counts,
    _finding_sort_key,
)
from quality_runner.code_quality_ledger import (
    build_resolution_ledger,
    render_resolution_ledger_markdown,
)
from quality_runner.code_quality_paths import _check_coverage, _string_or_none
from quality_runner.code_quality_ponytail import ponytail_findings
from quality_runner.code_quality_rules import _scan_file
from quality_runner.code_quality_similarity import collect_deduplicate_scan
from quality_runner.code_quality_skill_selection import scan_quality_skills_with_selection
from quality_runner.code_quality_summary import quality_summary_fields
from quality_runner.code_quality_unwired import unwired_findings
from quality_runner.core.audit_contracts import AuditPayload, TextScanScope
from quality_runner.evidence_redaction import redact_secret_like_source_lines
from quality_runner.incremental_analysis_cache import IncrementalAnalysisCache
from quality_runner.scan_scope import (
    DEFAULT_FAT_ROUTER_LINES as _DEFAULT_FAT_ROUTER_LINES,
)
from quality_runner.scan_scope import (
    DEFAULT_LARGE_FILE_LINES as _DEFAULT_LARGE_FILE_LINES,
)
from quality_runner.scan_scope import (
    create_text_scan_scope,
    discover_text_files,
    effective_scan_exclusions,
    generated_paths,
    scan_budget_summary,
    skipped_path_summary,
    structural_scan_policy,
)
from quality_runner.schema_constants import CODE_QUALITY_SCAN_SCHEMA

__all__ = [
    "build_resolution_ledger",
    "create_code_quality_scan",
    "preview_ignored_paths",
    "render_resolution_ledger_markdown",
]

DEFAULT_LARGE_FILE_LINES = _DEFAULT_LARGE_FILE_LINES
DEFAULT_FAT_ROUTER_LINES = _DEFAULT_FAT_ROUTER_LINES


def create_code_quality_scan(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
    skill_review_report: dict[str, Any] | None = None,
    require_skill_review_coverage: bool = False,
    text_scan_scope: TextScanScope | None = None,
    persist_cache: bool = True,
    cache_root: Path | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    policy = structural_scan_policy(config)
    disabled_groups = set(policy["disabled_rule_groups"])
    scope = text_scan_scope or create_text_scan_scope(
        root,
        scan=scan,
        config=config,
        module="code_quality",
    )
    skipped_files = list(scope.skipped_files)
    analysis_cache = IncrementalAnalysisCache(
        root,
        analysis_kind="code-quality",
        config=config,
        persist=persist_cache,
        cache_root=cache_root,
    )
    findings: list[dict[str, Any]] = []
    extracted_functions: list[dict[str, Any]] = []
    accountability: list[dict[str, Any]] = []
    scanned_files: list[dict[str, Any]] = []

    for file_info in scope.files:
        relative_path = file_info.path
        source_text = file_info.text
        source_lines = file_info.lines
        file_result = analysis_cache.get_or_compute(
            relative_path=relative_path,
            source_text=source_text,
            compute=lambda relative_path=relative_path, source_lines=source_lines: (
                _analyze_code_quality_file(
                    relative_path=relative_path,
                    source_lines=source_lines,
                    disabled_groups=disabled_groups,
                    large_file_lines=policy["large_file_lines"],
                    fat_router_lines=policy["fat_router_lines"],
                )
            ),
            validate=_valid_code_quality_file_result,
        )
        lines = _string_list_result(file_result, "redacted_lines")
        text = "\n".join(lines)
        scanned_files.append({"path": relative_path, "text": text, "lines": lines})
        accountability.append(
            {
                "path": relative_path,
                "line_count": len(lines),
                "sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                "scan_status": "scanned",
                "check_coverage": _check_coverage(relative_path),
            }
        )
        findings.extend(_dict_list_result(file_result, "findings"))
        extracted_functions.extend(_dict_list_result(file_result, "extracted_functions"))

    semantic_similarity_clusters = 0
    semantic_similarity_tools: dict[str, str] = {}
    semantic_similarity_cache: dict[str, Any] = {}
    (
        duplicate_clusters,
        deduplicate_findings,
        semantic_similarity_clusters,
        semantic_similarity_tools,
        semantic_similarity_cache,
    ) = collect_deduplicate_scan(
        root,
        extracted_functions=extracted_functions,
        scanned_files=scanned_files,
        policy=policy,
        disabled_groups=disabled_groups,
        persist_cache=persist_cache,
        cache_root=cache_root,
    )
    findings.extend(deduplicate_findings)

    if "ponytail" not in disabled_groups:
        findings.extend(ponytail_findings(scanned_files))

    if "speed" not in disabled_groups:
        findings.extend(bundle_budget_findings(root))

    if "integrate" not in disabled_groups:
        findings.extend(unwired_findings(scanned_files, config))

    findings.extend(architecture_findings(scanned_files, config))
    skill_findings, skill_coverage, quality_skills, skill_selection = (
        scan_quality_skills_with_selection(
            root,
            scanned_files,
            config,
            skill_review_report,
            require_review_coverage=require_skill_review_coverage,
        )
    )
    findings.extend(skill_findings)

    sorted_findings = sorted(findings, key=_finding_sort_key)
    for index, finding in enumerate(sorted_findings, start=1):
        finding["id"] = f"CQ-{index:04d}"

    return {
        "schema": CODE_QUALITY_SCAN_SCHEMA,
        "run_id": _string_or_none(scan.get("run_id")),
        "repo_root": str(root),
        "scan_exclusion_scope": "code_quality",
        "scan_exclusions": list(scope.scan_exclusions),
        "summary": {
            "total_files": len(accountability),
            "total_lines": sum(item["line_count"] for item in accountability),
            "total_findings": len(sorted_findings),
            "findings_by_category": _counts(sorted_findings, "category", CATEGORY_ORDER),
            "findings_by_severity": _counts(
                sorted_findings, "severity", ["warning", "observation"]
            ),
            "duplicate_clusters": len(duplicate_clusters),
            "semantic_similarity_clusters": semantic_similarity_clusters,
            "semantic_similarity_backend": policy["similarity_backend"],
            "semantic_similarity_tools": semantic_similarity_tools,
            **quality_summary_fields(
                backend=policy["similarity_backend"],
                enabled=policy["similarity_enabled"],
                disabled_groups=disabled_groups,
                semantic_similarity_tools=semantic_similarity_tools,
                accountability=accountability,
            ),
            "scan_budget": scan_budget_summary(
                scanned_files=len(accountability),
                max_text_files=scope.max_text_files,
                skipped_files=skipped_files,
            ),
            **skipped_path_summary(skipped_files),
        },
        "accountability": accountability,
        "findings": sorted_findings,
        "duplicate_clusters": duplicate_clusters,
        "skipped_files": sorted(skipped_files, key=_skipped_file_path),
        "quality_skills": quality_skills,
        "skill_coverage": skill_coverage,
        "skill_selection": skill_selection,
        "semantic_similarity_cache": semantic_similarity_cache,
        "analysis_cache": analysis_cache.evidence(considered_files=len(scope.files)),
    }


def _analyze_code_quality_file(
    *,
    relative_path: str,
    source_lines: list[str],
    disabled_groups: set[str],
    large_file_lines: int,
    fat_router_lines: int,
) -> dict[str, object]:
    lines = redact_secret_like_source_lines(source_lines)
    text = "\n".join(lines)
    return {
        "redacted_lines": lines,
        "findings": _scan_file(
            relative_path=relative_path,
            text=text,
            lines=lines,
            disabled_groups=disabled_groups,
            large_file_lines=large_file_lines,
            fat_router_lines=fat_router_lines,
        ),
        "extracted_functions": _extract_functions(relative_path, lines),
    }


def _valid_code_quality_file_result(result: dict[str, object]) -> bool:
    return (
        _string_list_result(result, "redacted_lines") is not None
        and _dict_list_result(result, "findings") is not None
        and _dict_list_result(result, "extracted_functions") is not None
    )


def _string_list_result(result: dict[str, object], key: str) -> list[str]:
    value = result.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"invalid cached code-quality result field: {key}")
    return list(value)


def _dict_list_result(result: dict[str, object], key: str) -> list[dict[str, Any]]:
    value = result.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"invalid cached code-quality result field: {key}")
    return [cast(dict[str, Any], item) for item in value]


def preview_ignored_paths(
    repo_root: Path,
    *,
    config: dict[str, Any],
    scan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    root = repo_root.expanduser().resolve()
    policy = structural_scan_policy(config)
    skipped_files: list[AuditPayload] = []
    discover_text_files(
        root,
        skipped_files=skipped_files,
        generated_paths=generated_paths(scan or {}),
        include_ignored_paths=set(policy["include_ignored_paths"]),
        scan_exclusions=effective_scan_exclusions(root, config, module="code_quality"),
        max_text_files=policy["max_text_files"],
    )
    return [
        item
        for item in sorted(skipped_files, key=_skipped_file_path)
        if item.get("reason") == "ignored directory"
    ]


def _skipped_file_path(item: AuditPayload) -> str:
    path = item.get("path")
    return path if isinstance(path, str) else ""
