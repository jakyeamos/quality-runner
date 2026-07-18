from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from quality_runner.code_quality_paths import _split_lines
from quality_runner.core.audit_contracts import AuditPayload, TextScanScope
from quality_runner.incremental_analysis_cache import IncrementalAnalysisCache
from quality_runner.scan_exclusions import effective_scan_exclusions, matches_scan_exclusion
from quality_runner.scan_scope import discover_text_files
from quality_runner.schema_constants import SECURITY_SCAN_SCHEMA
from quality_runner.security.agent_gates import build_agent_review_gates
from quality_runner.security.candidates import scan_security_candidates, taxonomy_payload
from quality_runner.security.capabilities import (
    detect_security_capabilities,
    merge_security_capabilities,
)
from quality_runner.security.config import security_settings
from quality_runner.security_surface_paths import is_api_route_path, is_webhook_path

RAW_CONTENT_MARKERS = (
    "dangerouslysetinnerhtml",
    ".innerhtml",
    "v-html",
    "raw_html",
    "rawhtml",
    "render_raw_html",
)
RAW_CONTENT_SUFFIXES = {".html", ".js", ".jsx", ".svelte", ".ts", ".tsx", ".vue"}
MAX_SURFACE_CONTENT_BYTES = 250_000


def create_security_scan(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
    standards_packet: dict[str, Any] | None = None,
    text_scan_scope: TextScanScope | None = None,
    persist_cache: bool = True,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    settings = security_settings(config)
    if not settings["enabled"]:
        disabled_scan = _disabled_security_scan(
            scan=scan,
            repo_root=root,
            scan_exclusions=effective_scan_exclusions(root, config, module="security"),
        )
        disabled_scan["analysis_cache"] = _disabled_cache_evidence(
            root,
            config,
            persist_cache=persist_cache,
        )
        return disabled_scan

    standards = standards_packet or {}
    scan_exclusions = effective_scan_exclusions(root, config, module="security")
    surfaces = detect_security_surfaces(
        root,
        scan=scan,
        scan_exclusions=scan_exclusions,
        text_scan_scope=text_scan_scope,
    )
    scanned_files = _scan_files(
        root,
        scan=scan,
        config=config,
        text_scan_scope=text_scan_scope,
        scan_exclusions=scan_exclusions,
    )
    disabled_groups = settings["disabled_rule_groups"]
    analysis_cache = IncrementalAnalysisCache(
        root,
        analysis_kind="security",
        config=config,
        context={
            "disabled_rule_groups": disabled_groups,
            "surfaces": surfaces,
        },
        persist=persist_cache,
    )
    candidates: list[dict[str, Any]] = []
    for file_info in scanned_files:
        relative_path = str(file_info["path"])
        source_text = str(file_info.get("text", ""))
        file_result = analysis_cache.get_or_compute(
            relative_path=relative_path,
            source_text=source_text,
            compute=lambda file_info=file_info: {
                "candidates": scan_security_candidates(
                    scanned_files=[file_info],
                    disabled_groups=disabled_groups,
                    surfaces=surfaces,
                )
            },
            validate=_valid_security_file_result,
            content_sha256=_content_sha256(file_info),
        )
        candidates.extend(_candidate_list_result(file_result))
    _renumber_security_candidate_ids(candidates)
    available, missing = detect_security_capabilities(
        scan=scan,
        standards_packet=standards,
        config=config,
        surfaces=surfaces,
    )
    agent_review_gates = build_agent_review_gates(
        surfaces=surfaces,
        candidates=candidates,
        settings=settings,
    )

    by_category: dict[str, int] = {}
    for candidate in candidates:
        category = str(candidate.get("category") or "unknown")
        by_category[category] = by_category.get(category, 0) + 1

    return {
        "schema": SECURITY_SCAN_SCHEMA,
        "run_id": _string_or_none(scan.get("run_id")),
        "repo_root": str(root),
        "scan_exclusion_scope": "security",
        "scan_exclusions": scan_exclusions,
        "summary": {
            "total_candidates": len(candidates),
            "candidates_by_category": by_category,
            "agent_review_gates": len(agent_review_gates),
            "missing_security_capabilities": len(missing),
            "available_security_capabilities": len(available),
        },
        "taxonomy": taxonomy_payload(),
        "candidates": candidates,
        "agent_review_gates": agent_review_gates,
        "missing_capabilities": missing,
        "available_capabilities": available,
        "surfaces": surfaces,
        "analysis_cache": analysis_cache.evidence(considered_files=len(scanned_files)),
        "settings": {
            "enabled": settings["enabled"],
            "agent_review_gates": settings["agent_review_gates"],
            "require_security_baseline": settings["require_security_baseline"],
        },
    }


def merge_security_into_capability_map(
    capability_map: dict[str, Any],
    security_scan: dict[str, Any],
) -> dict[str, Any]:
    if security_scan.get("settings", {}).get("enabled") is False:
        return capability_map
    merged = merge_security_capabilities(
        capability_map,
        available=security_scan.get("available_capabilities", []),
        missing=security_scan.get("missing_capabilities", []),
        agent_review_gates=security_scan.get("agent_review_gates", []),
    )
    readiness = merged.get("readiness")
    surfaces = security_scan.get("surfaces")
    if (
        isinstance(readiness, dict)
        and readiness.get("profile") == "release"
        and isinstance(surfaces, dict)
        and surfaces.get("publication_visibility") is True
    ):
        required = [
            item for item in readiness.get("required_gate_ids", []) if isinstance(item, str)
        ]
        unresolved = [
            item for item in readiness.get("unresolved_gate_ids", []) if isinstance(item, str)
        ]
        if "publication_visibility_review" not in required:
            required.append("publication_visibility_review")
        if "publication_visibility_review" not in unresolved:
            unresolved.append("publication_visibility_review")
        merged["readiness"] = {
            **readiness,
            "status": "blocked",
            "required_gate_ids": required,
            "unresolved_gate_ids": sorted(unresolved),
        }
    return merged


def detect_security_surfaces(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    scan_exclusions: list[str] | None = None,
    text_scan_scope: TextScanScope | None = None,
) -> dict[str, bool]:
    surfaces = {
        "api_routes": False,
        "webhooks": False,
        "dependency_manifest": False,
        "dangerous_sinks": False,
        "client_framework": False,
        "publication_visibility": False,
    }
    if text_scan_scope is not None:
        files_by_path = {file_info.path: file_info.text for file_info in text_scan_scope.files}
        for relative_path in text_scan_scope.security_surface_paths:
            _record_security_surface(surfaces, relative_path, Path(relative_path).name)
            if _raw_content_surface_text(relative_path, files_by_path.get(relative_path, "")):
                surfaces["publication_visibility"] = True
    else:
        for path in repo_root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(repo_root).as_posix()
            if scan_exclusions and matches_scan_exclusion(relative, scan_exclusions):
                continue
            if any(part.startswith(".") for part in path.parts) and (
                ".quality-runner" in path.parts or ".git" in path.parts
            ):
                continue
            _record_security_surface(surfaces, relative, path.name)
            if _raw_content_surface(path, relative):
                surfaces["publication_visibility"] = True

    languages = scan.get("languages")
    if isinstance(languages, list) and "javascript" in languages:
        surfaces["client_framework"] = True
    return surfaces


def _scan_files(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
    scan_exclusions: list[str] | None = None,
    text_scan_scope: TextScanScope | None = None,
) -> list[dict[str, Any]]:
    if text_scan_scope is not None:
        return [
            {"path": file_info.path, "text": file_info.text, "lines": file_info.lines}
            for file_info in text_scan_scope.files
        ]

    effective_exclusions = scan_exclusions or effective_scan_exclusions(
        repo_root,
        config,
        module="security",
    )
    include_ignored_paths: set[str] = set()
    structural = config.get("structural_scan")
    if isinstance(structural, dict):
        paths = structural.get("include_ignored_paths")
        if isinstance(paths, list):
            include_ignored_paths = {item for item in paths if isinstance(item, str)}
    generated_paths: set[str] = set()
    generated = scan.get("generated_code")
    if isinstance(generated, list):
        generated_paths = {item for item in generated if isinstance(item, str)}
    skipped_files: list[AuditPayload] = []
    max_text_files = 5000
    if isinstance(structural, dict) and isinstance(structural.get("max_text_files"), int):
        max_text_files = structural["max_text_files"]

    scanned: list[dict[str, Any]] = []
    for path in discover_text_files(
        repo_root,
        skipped_files=skipped_files,
        generated_paths=generated_paths,
        include_ignored_paths=include_ignored_paths,
        scan_exclusions=effective_exclusions,
        max_text_files=max_text_files,
    ):
        relative_path = path.relative_to(repo_root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned.append(
            {
                "path": relative_path,
                "text": text,
                "lines": _split_lines(text),
            }
        )
    return scanned


def _record_security_surface(
    surfaces: dict[str, bool],
    relative_path: str,
    file_name: str,
) -> None:
    if is_api_route_path(relative_path):
        surfaces["api_routes"] = True
    if is_webhook_path(relative_path):
        surfaces["webhooks"] = True
    if file_name in {"package.json", "pyproject.toml", "Cargo.toml", "go.mod"}:
        surfaces["dependency_manifest"] = True
    lowered = relative_path.lower()
    if any(
        marker in lowered
        for marker in (
            "publish",
            "publication",
            "reader",
            "draft",
            "media",
            "visibility",
            "raw-html",
            "raw_html",
            "rawhtml",
            "content",
            "visibility-boundary",
            "access-boundary",
            "public_",
            "public-",
            "public/",
            "private_",
            "private-",
            "private/",
        )
    ):
        surfaces["publication_visibility"] = True


def _raw_content_surface(path: Path, relative: str) -> bool:
    if path.suffix.lower() not in RAW_CONTENT_SUFFIXES:
        return False
    if relative.startswith(("quality_runner/security/", ".quality-runner/")):
        return False
    try:
        if path.stat().st_size > MAX_SURFACE_CONTENT_BYTES:
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return _raw_content_surface_text(relative, text)


def _raw_content_surface_text(relative: str, text: str) -> bool:
    if Path(relative).suffix.lower() not in RAW_CONTENT_SUFFIXES:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in RAW_CONTENT_MARKERS)


def _disabled_security_scan(
    *,
    scan: dict[str, Any],
    repo_root: Path,
    scan_exclusions: list[str],
) -> dict[str, Any]:
    return {
        "schema": SECURITY_SCAN_SCHEMA,
        "run_id": _string_or_none(scan.get("run_id")),
        "repo_root": str(repo_root),
        "scan_exclusion_scope": "security",
        "scan_exclusions": scan_exclusions,
        "summary": {
            "total_candidates": 0,
            "candidates_by_category": {},
            "agent_review_gates": 0,
            "missing_security_capabilities": 0,
            "available_security_capabilities": 0,
        },
        "taxonomy": taxonomy_payload(),
        "candidates": [],
        "agent_review_gates": [],
        "missing_capabilities": [],
        "available_capabilities": [],
        "surfaces": {},
        "settings": {"enabled": False},
    }


def _disabled_cache_evidence(
    repo_root: Path,
    config: dict[str, Any],
    *,
    persist_cache: bool,
) -> dict[str, object]:
    cache = IncrementalAnalysisCache(
        repo_root,
        analysis_kind="security",
        config=config,
        context={"enabled": False},
        persist=persist_cache,
    )
    evidence = cache.evidence(considered_files=0)
    evidence["status"] = "disabled"
    return evidence


def _valid_security_file_result(result: dict[str, object]) -> bool:
    return _candidate_list_result(result) is not None


def _candidate_list_result(result: dict[str, object]) -> list[dict[str, Any]]:
    value = result.get("candidates")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("invalid cached security result field: candidates")
    return [dict(item) for item in value]


def _renumber_security_candidate_ids(candidates: list[dict[str, Any]]) -> None:
    for index, candidate in enumerate(candidates, start=1):
        category = str(candidate.get("category", "candidate")).replace("-", "_")
        candidate["id"] = f"SEC-{category}-{index:04d}"


def _content_sha256(file_info: dict[str, Any]) -> str | None:
    value = file_info.get("content_sha256")
    if isinstance(value, str) and value:
        return value
    text = file_info.get("text")
    if isinstance(text, str):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return None


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
