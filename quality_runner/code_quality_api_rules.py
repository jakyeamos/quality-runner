from __future__ import annotations

import re
from typing import Any

from quality_runner.code_quality_findings import _finding
from quality_runner.code_quality_paths import (
    _is_javascript_source_file,
    _verification_for_path,
)

API_BOUNDARY_PATTERNS = (
    r"(?:^|/)api(?:/|$)",
    r"(?:^|/)routes?(?:/|$)",
    r"(?:^|/)routers?(?:/|$)",
    r"(?:^|/)server(?:/|$)",
)
VALIDATION_MARKERS = (
    ".input(",
    ".parse(",
    ".safeParse(",
    "Create",
    "Schema",
    "schema",
    "validate(",
    "validator",
    "z.object(",
    "yup.",
    "Joi.",
    "joi.",
    "valibot",
    "superstruct",
    "TypeBox",
)
PAGINATION_MARKERS = (
    "cursor",
    "limit",
    "offset",
    "page",
    "pageSize",
    "pagination",
    "skip",
    "take",
)


def _api_line_findings(relative_path: str, line: str, line_number: int) -> list[dict[str, Any]]:
    if not _is_javascript_source_file(relative_path):
        return []
    if not (
        _looks_like_api_boundary(relative_path, line)
        and re.search(
            r"\b(?:Response\.json|\.json)\s*\(\s*{\s*(?:message|error)\s*:",
            line,
        )
        and not re.search(r"\bcode\s*:", line)
    ):
        return []
    return [
        _finding(
            category="harden",
            severity="warning",
            confidence="medium",
            file=relative_path,
            line=line_number,
            rule_id="inconsistent-error-envelope",
            evidence=line,
            expected_improvement="Return the project error envelope with a stable code and message.",
            risk="Inconsistent error shapes force clients to branch around endpoint quirks.",
            verification=_verification_for_path(relative_path),
            remediation_bucket="API hardening and contract consistency",
        )
    ]


def _api_contract_findings(relative_path: str, text: str, lines: list[str]) -> list[dict[str, Any]]:
    if not _is_javascript_source_file(relative_path) or not _looks_like_api_boundary(
        relative_path, text
    ):
        return []

    findings: list[dict[str, Any]] = []
    if _uses_external_input(text) and not _has_boundary_validation(text):
        line_number, evidence = _first_matching_line(
            lines,
            r"\b(?:req\.body|req\.query|req\.params|request\.json|searchParams|body|input)\b",
        )
        findings.append(
            _finding(
                category="harden",
                severity="warning",
                confidence="medium",
                file=relative_path,
                line=line_number,
                rule_id="api-route-missing-boundary-validation",
                evidence=evidence,
                expected_improvement="Validate external input at the route or procedure boundary.",
                risk="Unvalidated API input lets hostile data cross into domain logic.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="API hardening and boundary validation",
            )
        )

    if _looks_like_collection_endpoint(relative_path, text) and not _has_pagination(text):
        line_number, evidence = _first_matching_line(
            lines,
            r"\b(?:findMany|SELECT\s+\*|\.select\s*\(|list[A-Z_]|getAll|getMany|"
            r"export\s+async\s+function\s+GET|Response\.json)\b",
        )
        findings.append(
            _finding(
                category="speed",
                severity="warning",
                confidence="medium",
                file=relative_path,
                line=line_number,
                rule_id="list-endpoint-missing-pagination",
                evidence=evidence,
                expected_improvement="Add limit/cursor/page parameters and bounded defaults.",
                risk="Unbounded list endpoints become latency and memory failures as data grows.",
                verification=_verification_for_path(relative_path),
                remediation_bucket="API performance and pagination",
            )
        )
    return findings


def _looks_like_api_boundary(relative_path: str, text: str) -> bool:
    if any(re.search(pattern, relative_path) for pattern in API_BOUNDARY_PATTERNS):
        return True
    return (
        re.search(
            r"\b(?:export\s+async\s+function\s+(?:GET|POST|PUT|PATCH|DELETE)|"
            r"(?:app|router)\.(?:get|post|put|patch|delete)\s*\(|"
            r"(?:publicProcedure|protectedProcedure|adminProcedure)\b)",
            text,
        )
        is not None
    )


def _uses_external_input(text: str) -> bool:
    return (
        re.search(
            r"\b(?:req\.(?:body|query|params)|request\.json\s*\(|searchParams|ctx\.input|input)\b",
            text,
        )
        is not None
    )


def _has_boundary_validation(text: str) -> bool:
    return any(marker in text for marker in VALIDATION_MARKERS)


def _looks_like_collection_endpoint(relative_path: str, text: str) -> bool:
    if re.search(
        r"\b(?:findMany\s*\(|SELECT\s+\*|\.select\s*\(|list[A-Z_]|getAll|getMany)\b",
        text,
        re.IGNORECASE,
    ):
        return True
    if not re.search(r"\bexport\s+async\s+function\s+GET\b", text):
        return False
    if not _path_suggests_collection(relative_path):
        return False
    return (
        re.search(
            r"\b(?:Response\.json\s*\(\s*(?:rows|items|results|records|users|posts|todos)\b|"
            r"return\s+\[(?:.|\n)*\])",
            text,
            re.IGNORECASE,
        )
        is not None
    )


def _has_pagination(text: str) -> bool:
    return any(re.search(rf"\b{re.escape(marker)}\b", text) for marker in PAGINATION_MARKERS)


def _path_suggests_collection(relative_path: str) -> bool:
    parts = [part for part in relative_path.split("/") if part not in {"api", "route.ts"}]
    return any(re.search(r"[a-z][a-z0-9_-]*s$", part) for part in parts)


def _first_matching_line(lines: list[str], pattern: str) -> tuple[int, str]:
    for index, line in enumerate(lines, start=1):
        if re.search(pattern, line, re.IGNORECASE):
            return index, line
    return 1, lines[0] if lines else ""
