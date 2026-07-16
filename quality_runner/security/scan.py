from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.code_quality import _discover_text_files
from quality_runner.code_quality_paths import _split_lines
from quality_runner.scan_exclusions import gitignore_scan_exclusions, resolve_scan_exclusions
from quality_runner.schema_constants import SECURITY_SCAN_SCHEMA
from quality_runner.security.agent_gates import build_agent_review_gates
from quality_runner.security.candidates import scan_security_candidates, taxonomy_payload
from quality_runner.security.capabilities import (
    detect_security_capabilities,
    merge_security_capabilities,
)
from quality_runner.security.config import security_settings

API_ROUTE_MARKERS = (
    "app/api/",
    "pages/api/",
    "src/routes/",
    "routes/api/",
    "api/",
)
WEBHOOK_MARKERS = ("webhook", "webhooks")
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
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    settings = security_settings(config)
    if not settings["enabled"]:
        return _disabled_security_scan(scan=scan, repo_root=root)

    standards = standards_packet or {}
    surfaces = detect_security_surfaces(root, scan=scan)
    scanned_files = _scan_files(root, scan=scan, config=config)
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


def detect_security_surfaces(repo_root: Path, *, scan: dict[str, Any]) -> dict[str, bool]:
    surfaces = {
        "api_routes": False,
        "webhooks": False,
        "dependency_manifest": False,
        "dangerous_sinks": False,
        "client_framework": False,
        "publication_visibility": False,
    }
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(repo_root).as_posix()
        if any(part.startswith(".") for part in path.parts) and (
            ".quality-runner" in path.parts or ".git" in path.parts
        ):
            continue
        if any(marker in relative for marker in API_ROUTE_MARKERS):
            surfaces["api_routes"] = True
        if any(marker in relative.lower() for marker in WEBHOOK_MARKERS):
            surfaces["webhooks"] = True
        if path.name in {"package.json", "pyproject.toml", "Cargo.toml", "go.mod"}:
            surfaces["dependency_manifest"] = True
        lowered = relative.lower()
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
        if _raw_content_surface(path, relative):
            surfaces["publication_visibility"] = True

    languages = scan.get("languages")
    if isinstance(languages, list) and "javascript" in languages:
        surfaces["client_framework"] = True
    return surfaces


def _raw_content_surface(path: Path, relative: str) -> bool:
    if path.suffix.lower() not in RAW_CONTENT_SUFFIXES:
        return False
    if relative.startswith(("quality_runner/security/", ".quality-runner/")):
        return False
    try:
        if path.stat().st_size > MAX_SURFACE_CONTENT_BYTES:
            return False
        text = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False
    return any(marker in text for marker in RAW_CONTENT_MARKERS)


def _scan_files(
    repo_root: Path,
    *,
    scan: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
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
    skipped_files: list[dict[str, Any]] = []
    max_text_files = 5000
    if isinstance(structural, dict) and isinstance(structural.get("max_text_files"), int):
        max_text_files = structural["max_text_files"]

    scanned: list[dict[str, Any]] = []
    for path in _discover_text_files(
        repo_root,
        skipped_files,
        generated_paths,
        include_ignored_paths,
        scan_exclusions,
        max_text_files,
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
