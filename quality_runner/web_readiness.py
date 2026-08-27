from __future__ import annotations

import gzip
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from quality_runner import web_readiness_deployment
from quality_runner.code_quality_bundles import JS_BUNDLE_DIRS
from quality_runner.web_readiness_config import (
    DEFAULT_BUNDLE_BUDGET_GZIP_BYTES,
    DEFAULT_TOTAL_BUNDLE_BUDGET_GZIP_BYTES,
)

REPORT_SCHEMA = "quality-runner-web-readiness/v1"
DEPLOYMENT_EVIDENCE_SCHEMA = web_readiness_deployment.DEPLOYMENT_EVIDENCE_SCHEMA
DEFAULT_REPORT_PATH = ".quality-runner/web-readiness.json"
SOURCE_SUFFIXES = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte"}
IGNORED_PARTS = {
    ".git",
    ".quality-runner",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "build",
    "dist",
    "node_modules",
    "out",
    "vendor",
}


def has_web_surface(repo_root: Path) -> bool:
    """Return whether the bounded web-readiness scanner finds supported source."""
    return bool(_source_files(repo_root.expanduser().resolve()))


def create_web_readiness_report(
    repo_root: Path,
    *,
    config: dict[str, Any] | None = None,
    deployment_evidence_path: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    web_config = dict((config or {}).get("web_readiness") or {})
    applicability = str(web_config.get("applicability") or "unknown")
    reason = web_config.get("reason")
    observed_at = generated_at or datetime.now(UTC).isoformat()
    branch, head_sha = _git_provenance(root)

    if applicability == "not_applicable":
        return _report(
            root=root,
            observed_at=observed_at,
            branch=branch,
            head_sha=head_sha,
            applicability=applicability,
            applicability_reason=str(
                reason or "Repository policy marks web readiness not applicable."
            ),
            checks=[],
            target={"kind": "source", "commit": head_sha},
        )

    checks = _source_checks(root)
    checks.append(_bundle_check(root, web_config))
    target: dict[str, Any] = {"kind": "source", "commit": head_sha}
    route_config = web_config.get("routes")
    configured_routes = (
        [item for item in cast(list[object], route_config) if isinstance(item, str)]
        if isinstance(route_config, list)
        else []
    )

    if deployment_evidence_path is not None:
        deployment, error = web_readiness_deployment.load_deployment_evidence(
            deployment_evidence_path, head_sha=head_sha
        )
        if error is not None:
            checks.append(
                web_readiness_deployment.readiness_check(
                    "deployment_evidence",
                    "Deployment evidence",
                    "baseline",
                    "block",
                    "blocked",
                    "deployment_verified",
                    error,
                )
            )
        elif deployment is not None:
            target = dict(deployment["target"])
            checks.extend(
                web_readiness_deployment.deployment_checks(
                    deployment, configured_routes=configured_routes
                )
            )
    else:
        checks.extend(
            [
                web_readiness_deployment.readiness_check(
                    "deployment_route_coverage",
                    "Deployment route coverage",
                    "baseline",
                    "block",
                    "unknown",
                    "deployment_verified",
                    "No project-owned browser deployment evidence was supplied.",
                ),
                web_readiness_deployment.readiness_check(
                    "console_errors",
                    "Console errors",
                    "baseline",
                    "block",
                    "unknown",
                    "deployment_verified",
                    "Console behavior requires project-owned browser deployment evidence.",
                ),
                web_readiness_deployment.readiness_check(
                    "asset_errors",
                    "Network and asset errors",
                    "baseline",
                    "block",
                    "unknown",
                    "deployment_verified",
                    "Network and asset behavior requires project-owned browser deployment evidence.",
                ),
            ]
        )

    applicability_reason = str(reason) if isinstance(reason, str) else None
    if applicability == "unknown" and not applicability_reason:
        applicability_reason = (
            "Set quality_runner.web_readiness.applicability before using this report as policy."
        )
    return _report(
        root=root,
        observed_at=observed_at,
        branch=branch,
        head_sha=head_sha,
        applicability=applicability,
        applicability_reason=applicability_reason,
        checks=checks,
        target=target,
    )


def write_web_readiness_report(report: dict[str, Any], output_path: Path) -> Path:
    path = output_path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def _report(
    *,
    root: Path,
    observed_at: str,
    branch: str | None,
    head_sha: str | None,
    applicability: str,
    applicability_reason: str | None,
    checks: list[dict[str, Any]],
    target: dict[str, Any],
) -> dict[str, Any]:
    effective_checks = _strongest_checks(checks)
    blocking = [item for item in effective_checks if item["policy"] == "block"]
    warning = [item for item in effective_checks if item["policy"] == "warn"]
    if applicability == "not_applicable":
        status = "not_applicable"
    elif applicability == "unknown":
        status = "unknown"
    elif any(item["status"] in {"failed", "blocked"} for item in blocking):
        status = "blocked"
    elif any(item["status"] == "unknown" for item in blocking):
        status = "unknown"
    elif any(item["status"] in {"failed", "blocked", "unknown"} for item in warning):
        status = "warnings"
    else:
        status = "ready"

    minimum_level = _minimum_passing_level(blocking)
    counts = {
        key: sum(1 for item in checks if item["status"] == key)
        for key in ("passed", "failed", "blocked", "unknown", "not_applicable")
    }
    return {
        "schema": REPORT_SCHEMA,
        "status": status,
        "generated_at": observed_at,
        "repository": {
            "path": str(root),
            "branch": branch,
            "head_sha": head_sha,
        },
        "applicability": {
            "status": applicability,
            "reason": applicability_reason,
        },
        "summary": {
            **counts,
            "check_count": len(checks),
            "blocking_check_count": len(blocking),
            "warning_check_count": len(warning),
            "minimum_verification_level": minimum_level,
        },
        "target": target,
        "checks": checks,
        "implementation_allowed": False,
    }


def _source_checks(root: Path) -> list[dict[str, Any]]:
    files = _source_files(root)
    combined = "\n".join(text for _, text in files)
    image_elements = re.findall(
        r"<(?:img|Image)\b[^>]*>", combined, flags=re.IGNORECASE | re.DOTALL
    )
    missing_alt = [item for item in image_elements if re.search(r"\balt\s*=", item) is None]

    language_found = bool(re.search(r"<html\b[^>]*\blang\s*=", combined, re.IGNORECASE | re.DOTALL))
    favicon_found = bool(
        re.search(
            r"<link\b[^>]*\brel\s*=\s*['\"][^'\"]*\bicon\b",
            combined,
            re.IGNORECASE | re.DOTALL,
        )
    ) or any((root / path).is_file() for path in ("public/favicon.ico", "app/favicon.ico"))
    title_found = bool(
        re.search(r"<title\b[^>]*>\s*[^<]+", combined, re.IGNORECASE | re.DOTALL)
        or re.search(r"\btitle\s*:\s*['\"][^'\"]+", combined)
    )
    heading_found = bool(re.search(r"<h1\b", combined, re.IGNORECASE))
    not_found_found = any(
        path.name.lower() in {"404.html", "404.tsx", "404.jsx", "not-found.tsx", "not-found.jsx"}
        for path, _ in files
    )
    meta_found = bool(
        re.search(
            r"<meta\b[^>]*\bname\s*=\s*['\"]description['\"]",
            combined,
            re.IGNORECASE | re.DOTALL,
        )
    )
    og_found = bool(
        re.search(
            r"<meta\b[^>]*\bproperty\s*=\s*['\"]og:image['\"]",
            combined,
            re.IGNORECASE | re.DOTALL,
        )
    )

    return [
        _boolean_source_check(
            "document_language",
            "Document language",
            "baseline",
            "block",
            language_found,
            "A language declaration was found in source.",
            "No HTML language declaration was found in supported source files.",
        ),
        web_readiness_deployment.readiness_check(
            "image_alternatives",
            "Image alternatives",
            "baseline",
            "block",
            "failed" if missing_alt else "passed" if image_elements else "unknown",
            "source_inferred",
            (
                f"{len(missing_alt)} of {len(image_elements)} source image elements lack an alt prop."
                if missing_alt
                else f"All {len(image_elements)} source image elements declare alt props."
                if image_elements
                else "No supported source image elements were found."
            ),
        ),
        _boolean_source_check(
            "favicon",
            "Favicon",
            "baseline",
            "block",
            favicon_found,
            "A favicon declaration or conventional asset was found.",
            "No favicon declaration or conventional asset was found.",
        ),
        _boolean_source_check(
            "route_titles",
            "Route titles",
            "baseline",
            "block",
            title_found,
            "A title declaration was found; route uniqueness still requires browser evidence.",
            "No title declaration was found in supported source files.",
        ),
        _boolean_source_check(
            "primary_heading",
            "Primary heading",
            "baseline",
            "block",
            heading_found,
            "A primary heading declaration was found; route counts still require browser evidence.",
            "No primary heading declaration was found in supported source files.",
        ),
        _boolean_source_check(
            "custom_404",
            "Custom 404",
            "baseline",
            "block",
            not_found_found,
            "A conventional not-found route was found; response behavior still requires deployment evidence.",
            "No conventional custom not-found route was found.",
        ),
        _boolean_source_check(
            "meta_description",
            "Meta description",
            "polish",
            "warn",
            meta_found,
            "A meta-description declaration was found.",
            "No static meta-description declaration was found.",
        ),
        _boolean_source_check(
            "social_image",
            "Social image",
            "polish",
            "warn",
            og_found,
            "An Open Graph image declaration was found.",
            "No static Open Graph image declaration was found.",
        ),
    ]


def _bundle_check(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    roots = config.get("build_roots") or list(JS_BUNDLE_DIRS)
    per_file_budget = int(
        config.get("bundle_budget_gzip_bytes") or DEFAULT_BUNDLE_BUDGET_GZIP_BYTES
    )
    total_budget = int(
        config.get("total_bundle_budget_gzip_bytes") or DEFAULT_TOTAL_BUNDLE_BUDGET_GZIP_BYTES
    )
    bundles: list[tuple[str, int]] = []
    for relative_root in roots:
        build_root = root / str(relative_root)
        if not build_root.is_dir():
            continue
        for path in sorted(build_root.rglob("*.js")):
            if not path.is_file() or path.name.endswith(".map"):
                continue
            bundles.append(
                (path.relative_to(root).as_posix(), len(gzip.compress(path.read_bytes())))
            )
    if not bundles:
        return web_readiness_deployment.readiness_check(
            "javascript_bundle_budget",
            "JavaScript bundle budget",
            "baseline",
            "block",
            "unknown",
            "artifact_inspected",
            "No supported production JavaScript artifacts were found; run the production build first.",
        )
    oversized = [(path, size) for path, size in bundles if size > per_file_budget]
    total = sum(size for _, size in bundles)
    failed = bool(oversized) or total > total_budget
    detail = (
        f"Inspected {len(bundles)} artifact(s): {total} total gzipped bytes; "
        f"per-file budget {per_file_budget}, total budget {total_budget}."
    )
    if oversized:
        detail += " Oversized: " + ", ".join(f"{path} ({size})" for path, size in oversized[:8])
    return web_readiness_deployment.readiness_check(
        "javascript_bundle_budget",
        "JavaScript bundle budget",
        "baseline",
        "block",
        "failed" if failed else "passed",
        "artifact_inspected",
        detail,
        evidence=[{"path": path, "gzip_bytes": size} for path, size in bundles[:100]],
    )


def _source_files(root: Path) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        try:
            files.append((path, path.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return files


def _git_provenance(root: Path) -> tuple[str | None, str | None]:
    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    return git("branch", "--show-current"), git("rev-parse", "HEAD")


def _boolean_source_check(
    check_id: str,
    label: str,
    category: str,
    policy: str,
    passed: bool,
    passed_detail: str,
    failed_detail: str,
) -> dict[str, Any]:
    return web_readiness_deployment.readiness_check(
        check_id,
        label,
        category,
        policy,
        "passed" if passed else "failed",
        "source_inferred",
        passed_detail if passed else failed_detail,
    )


def _minimum_passing_level(checks: list[dict[str, Any]]) -> str | None:
    passing = [item for item in checks if item["status"] == "passed"]
    if len(passing) != len(checks) or not passing:
        return None
    rank = {
        "source_inferred": 0,
        "artifact_inspected": 1,
        "browser_rendered": 2,
        "deployment_verified": 3,
    }
    return min(passing, key=lambda item: rank.get(str(item["verification_level"]), -1))[
        "verification_level"
    ]


def _strongest_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {
        "source_inferred": 0,
        "artifact_inspected": 1,
        "browser_rendered": 2,
        "deployment_verified": 3,
    }
    selected: dict[str, dict[str, Any]] = {}
    for check in checks:
        current = selected.get(str(check["id"]))
        if current is None or rank.get(str(check["verification_level"]), -1) > rank.get(
            str(current["verification_level"]), -1
        ):
            selected[str(check["id"])] = check
    return list(selected.values())
