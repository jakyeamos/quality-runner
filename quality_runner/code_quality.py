from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
from typing import Any

from quality_runner.code_quality_architecture import architecture_findings
from quality_runner.code_quality_duplicates import _extract_functions
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
from quality_runner.code_quality_paths import _check_coverage, _string_or_none
from quality_runner.code_quality_ponytail import ponytail_findings
from quality_runner.code_quality_rules import _scan_file
from quality_runner.code_quality_similarity import collect_deduplicate_scan
from quality_runner.code_quality_skills import scan_quality_skills
from quality_runner.code_quality_unwired import unwired_findings
from quality_runner.core.audit_contracts import AuditPayload, TextScanScope
from quality_runner.evidence_redaction import redact_secret_like_source_lines
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

DEFAULT_GZIPPED_JS_BUNDLE_BYTES = 200_000
DEFAULT_LARGE_FILE_LINES = _DEFAULT_LARGE_FILE_LINES
DEFAULT_FAT_ROUTER_LINES = _DEFAULT_FAT_ROUTER_LINES
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
    skill_review_report: dict[str, Any] | None = None,
    require_skill_review_coverage: bool = False,
    text_scan_scope: TextScanScope | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    policy = structural_scan_policy(config)
    disabled_groups = set(policy["disabled_rule_groups"])
    scope = text_scan_scope or create_text_scan_scope(root, scan=scan, config=config)
    skipped_files = list(scope.skipped_files)
    findings: list[dict[str, Any]] = []
    extracted_functions: list[dict[str, Any]] = []
    accountability: list[dict[str, Any]] = []
    scanned_files: list[dict[str, Any]] = []

    for file_info in scope.files:
        relative_path = file_info.path
        source_text = file_info.text
        source_lines = file_info.lines
        lines = redact_secret_like_source_lines(source_lines)
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

    semantic_similarity_clusters = 0
    semantic_similarity_tools: dict[str, str] = {}
    (
        duplicate_clusters,
        deduplicate_findings,
        semantic_similarity_clusters,
        semantic_similarity_tools,
    ) = collect_deduplicate_scan(
        root,
        extracted_functions=extracted_functions,
        policy=policy,
        disabled_groups=disabled_groups,
    )
    findings.extend(deduplicate_findings)

    if "ponytail" not in disabled_groups:
        findings.extend(ponytail_findings(scanned_files))

    if "speed" not in disabled_groups:
        findings.extend(_bundle_budget_findings(root))

    if "integrate" not in disabled_groups:
        findings.extend(unwired_findings(scanned_files, config))

    findings.extend(architecture_findings(scanned_files, config))
    skill_findings, skill_coverage, quality_skills = scan_quality_skills(
        repo_root=root,
        scanned_files=scanned_files,
        config=config,
        skill_review_report=skill_review_report,
        require_review_coverage=require_skill_review_coverage,
    )
    findings.extend(skill_findings)

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
            "semantic_similarity_clusters": semantic_similarity_clusters,
            "semantic_similarity_tools": semantic_similarity_tools,
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
    }


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
        scan_exclusions=effective_scan_exclusions(root, config),
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
