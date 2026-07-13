from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.code_quality_paths import _split_lines
from quality_runner.core.audit_contracts import AuditPayload, TextScanScope
from quality_runner.scan_exclusions import gitignore_scan_exclusions, resolve_scan_exclusions
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


def create_security_scan(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
    standards_packet: dict[str, Any] | None = None,
    text_scan_scope: TextScanScope | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    settings = security_settings(config)
    if not settings["enabled"]:
        return _disabled_security_scan(scan=scan, repo_root=root)

    standards = standards_packet or {}
    surfaces = detect_security_surfaces(root, scan=scan, text_scan_scope=text_scan_scope)
    scanned_files = _scan_files(
        root,
        scan=scan,
        config=config,
        text_scan_scope=text_scan_scope,
    )
    disabled_groups = settings["disabled_rule_groups"]
    candidates = scan_security_candidates(
        scanned_files=scanned_files,
        disabled_groups=disabled_groups,
        surfaces=surfaces,
    )
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
    return merge_security_capabilities(
        capability_map,
        available=security_scan.get("available_capabilities", []),
        missing=security_scan.get("missing_capabilities", []),
        agent_review_gates=security_scan.get("agent_review_gates", []),
    )


def detect_security_surfaces(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    text_scan_scope: TextScanScope | None = None,
) -> dict[str, bool]:
    surfaces = {
        "api_routes": False,
        "webhooks": False,
        "dependency_manifest": False,
        "dangerous_sinks": False,
        "client_framework": False,
    }
    if text_scan_scope is not None:
        for relative_path in text_scan_scope.security_surface_paths:
            _record_security_surface(surfaces, relative_path, Path(relative_path).name)
    else:
        for path in repo_root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(repo_root).as_posix()
            if any(part.startswith(".") for part in path.parts) and (
                ".quality-runner" in path.parts or ".git" in path.parts
            ):
                continue
            _record_security_surface(surfaces, relative, path.name)

    languages = scan.get("languages")
    if isinstance(languages, list) and "javascript" in languages:
        surfaces["client_framework"] = True
    return surfaces


def _scan_files(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
    text_scan_scope: TextScanScope | None,
) -> list[dict[str, Any]]:
    if text_scan_scope is not None:
        return [
            {"path": file_info.path, "text": file_info.text, "lines": file_info.lines}
            for file_info in text_scan_scope.files
        ]

    scan_exclusions = [
        *resolve_scan_exclusions(config),
        *gitignore_scan_exclusions(repo_root),
    ]
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
        scan_exclusions=scan_exclusions,
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


def _disabled_security_scan(*, scan: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    return {
        "schema": SECURITY_SCAN_SCHEMA,
        "run_id": _string_or_none(scan.get("run_id")),
        "repo_root": str(repo_root),
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


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
