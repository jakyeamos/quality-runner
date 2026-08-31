from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

DEPLOYMENT_EVIDENCE_SCHEMA = "quality-runner-web-deployment-evidence/v1"


def load_deployment_evidence(
    path: Path,
    *,
    head_sha: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"Deployment evidence could not be read: {error}"
    if not isinstance(payload, dict):
        return None, f"Deployment evidence must use schema {DEPLOYMENT_EVIDENCE_SCHEMA}."
    payload = cast(dict[str, Any], payload)
    if payload.get("schema") != DEPLOYMENT_EVIDENCE_SCHEMA:
        return None, f"Deployment evidence must use schema {DEPLOYMENT_EVIDENCE_SCHEMA}."
    target_value = payload.get("target")
    routes_value = payload.get("routes")
    if not isinstance(target_value, dict) or not isinstance(routes_value, list) or not routes_value:
        return None, "Deployment evidence requires a target and at least one route."
    target = cast(dict[str, Any], target_value)
    raw_routes = cast(list[object], routes_value)
    target_commit = target.get("commit")
    if head_sha and target_commit != head_sha:
        return None, "Deployment evidence commit does not match the repository HEAD."
    if target.get("kind") != "deployment" or not target.get("url"):
        return None, "Deployment evidence target must identify a deployment URL."
    if not all(
        isinstance(route, dict) and isinstance(cast(dict[str, Any], route).get("route"), str)
        for route in raw_routes
    ):
        return None, "Every deployment evidence route must be an object with a route string."
    payload["routes"] = [cast(dict[str, Any], route) for route in raw_routes]
    return payload, None


def deployment_checks(
    payload: dict[str, Any],
    *,
    configured_routes: list[str],
) -> list[dict[str, Any]]:
    routes_value = payload["routes"]
    raw_routes = cast(list[object], routes_value) if isinstance(routes_value, list) else []
    routes = [cast(dict[str, Any], item) for item in raw_routes if isinstance(item, dict)]
    required_routes = set(configured_routes)
    observed_routes = {str(item.get("route")) for item in routes if not item.get("not_found_probe")}
    route_gap = sorted(required_routes - observed_routes)
    normal = [item for item in routes if not item.get("not_found_probe")]
    not_found = [item for item in routes if item.get("not_found_probe")]

    titles = [str(item.get("title") or "").strip() for item in normal]
    title_pass = bool(normal) and not route_gap and all(titles) and len(set(titles)) == len(titles)
    return [
        _deployment_boolean_check(
            "deployment_route_coverage",
            "Deployment route coverage",
            "baseline",
            "block",
            bool(normal) and not route_gap,
            "All configured routes have browser evidence.",
            (
                f"Missing browser evidence for routes: {', '.join(route_gap)}"
                if route_gap
                else "No normal routes were observed."
            ),
            routes=route_gap,
        ),
        _deployment_boolean_check(
            "custom_404",
            "Custom 404",
            "baseline",
            "block",
            bool(not_found) and all(int(item.get("status_code") or 0) == 404 for item in not_found),
            "The not-found probe returned HTTP 404.",
            "No verified HTTP 404 not-found probe was recorded.",
            routes=[str(item.get("route")) for item in not_found],
        ),
        _deployment_boolean_check(
            "route_titles",
            "Route titles",
            "baseline",
            "block",
            title_pass,
            "Every observed route has a non-empty unique title.",
            "Observed route titles are missing, duplicated, or incomplete.",
            routes=[str(item.get("route")) for item in normal],
        ),
        _deployment_boolean_check(
            "primary_heading",
            "Primary heading",
            "baseline",
            "block",
            bool(normal)
            and all(int(item.get("primary_heading_count") or 0) == 1 for item in normal),
            "Every observed route has exactly one primary heading.",
            "At least one observed route does not have exactly one primary heading.",
            routes=[str(item.get("route")) for item in normal],
        ),
        _deployment_boolean_check(
            "document_language",
            "Document language",
            "baseline",
            "block",
            bool(normal) and all(str(item.get("html_lang") or "").strip() for item in normal),
            "Every observed route exposes a document language.",
            "At least one observed route lacks a document language.",
            routes=[str(item.get("route")) for item in normal],
        ),
        _deployment_boolean_check(
            "image_alternatives",
            "Image alternatives",
            "baseline",
            "block",
            bool(normal) and all(int(item.get("missing_alt_count") or 0) == 0 for item in normal),
            "Every rendered image has an alternative declaration.",
            "At least one observed route has rendered images without alternatives.",
            routes=[str(item.get("route")) for item in normal],
        ),
        _deployment_boolean_check(
            "console_errors",
            "Console errors",
            "baseline",
            "block",
            bool(normal) and all(int(item.get("console_error_count") or 0) == 0 for item in normal),
            "No browser console errors were recorded.",
            "Browser console errors were recorded on at least one route.",
            routes=[str(item.get("route")) for item in normal],
        ),
        _deployment_boolean_check(
            "asset_errors",
            "Network and asset errors",
            "baseline",
            "block",
            bool(normal)
            and all(
                int(item.get("network_error_count") or 0) == 0
                and int(item.get("asset_error_count") or 0) == 0
                for item in normal
            ),
            "No network or asset failures were recorded.",
            "Network or asset failures were recorded on at least one route.",
            routes=[str(item.get("route")) for item in normal],
        ),
        _deployment_boolean_check(
            "favicon",
            "Favicon",
            "baseline",
            "block",
            bool(normal) and all(item.get("favicon_loaded") is True for item in normal),
            "The favicon loaded on every observed route.",
            "The favicon was missing or failed to load on at least one route.",
            routes=[str(item.get("route")) for item in normal],
        ),
        _deployment_boolean_check(
            "meta_description",
            "Meta description",
            "polish",
            "warn",
            bool(normal)
            and all(str(item.get("meta_description") or "").strip() for item in normal),
            "Every observed route has a meta description.",
            "At least one observed route lacks a meta description.",
            routes=[str(item.get("route")) for item in normal],
        ),
        _deployment_boolean_check(
            "social_image",
            "Social image",
            "polish",
            "warn",
            bool(normal) and all(str(item.get("og_image") or "").strip() for item in normal),
            "Every observed route has an Open Graph image.",
            "At least one observed route lacks an Open Graph image.",
            routes=[str(item.get("route")) for item in normal],
        ),
    ]


def readiness_check(
    check_id: str,
    label: str,
    category: str,
    policy: str,
    status: str,
    verification_level: str,
    detail: str,
    *,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "category": category,
        "policy": policy,
        "status": status,
        "verification_level": verification_level,
        "detail": detail,
        "evidence": evidence or [],
    }


def _deployment_boolean_check(
    check_id: str,
    label: str,
    category: str,
    policy: str,
    passed: bool,
    passed_detail: str,
    failed_detail: str,
    *,
    routes: list[str],
) -> dict[str, Any]:
    return readiness_check(
        check_id,
        label,
        category,
        policy,
        "passed" if passed else "failed",
        "deployment_verified",
        passed_detail if passed else failed_detail,
        evidence=[{"route": route} for route in routes],
    )
