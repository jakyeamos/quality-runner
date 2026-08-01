"""Hash-bound handoff and command projections for Codex Security evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from quality_runner.evidence_contract import QUALITY_EVIDENCE_SCHEMA
from quality_runner.schema_constants import (
    CODEX_SECURITY_COMPARE_SCHEMA,
    CODEX_SECURITY_EVIDENCE_SCHEMA,
    CODEX_SECURITY_HANDOFF_SCHEMA,
    CODEX_SECURITY_RESULT_SCHEMA,
)
from quality_runner.security._codex_common import (
    _validation_result,
    canonical_hash,
    canonical_json,
)
from quality_runner.security._codex_compare import validate_codex_compare
from quality_runner.security._codex_evidence import validate_codex_evidence


def export_codex_handoff(comparison: Mapping[str, Any]) -> dict[str, Any]:
    """Create a self-contained, hash-bound handoff from a valid comparison."""

    validation = validate_codex_compare(comparison)
    if not validation["passed"]:
        raise ValueError("invalid Codex comparison: " + "; ".join(validation["errors"]))

    matches = list(comparison["matches"])
    unknown_count = sum(1 for match in matches if match["status"] == "unknown")
    actionable = [match for match in matches if match["status"] in {"new", "present", "unknown"}]
    if not _comparison_coverage_complete(comparison) or unknown_count:
        handoff_status = "unknown"
    elif actionable:
        handoff_status = "review-required"
    else:
        handoff_status = "clean"
    handoff: dict[str, Any] = {
        "schema": CODEX_SECURITY_HANDOFF_SCHEMA,
        "contract_schema": QUALITY_EVIDENCE_SCHEMA,
        "source": "codex-security",
        "status": handoff_status,
        "implementation_allowed": False,
        "baseline_evidence_hash": comparison["baseline_hash"],
        "current_evidence_hash": comparison["current_hash"],
        "comparison_hash": comparison["comparison_hash"],
        "input_hashes": {
            "baseline": comparison["baseline_hash"],
            "current": comparison["current_hash"],
            "comparison": comparison["comparison_hash"],
        },
        "coverage": comparison["coverage"],
        "summary": comparison["summary"],
        "findings": actionable,
        "comparison": comparison,
    }
    handoff["handoff_hash"] = canonical_hash(handoff, exclude=("handoff_hash",))
    return handoff


def validate_codex_handoff(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a handoff and ensure its embedded comparison is still bound."""

    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("schema") != CODEX_SECURITY_HANDOFF_SCHEMA:
        errors.append("Codex handoff schema is invalid")
    if payload.get("contract_schema") != QUALITY_EVIDENCE_SCHEMA:
        errors.append("Codex handoff contract_schema is invalid")
    if payload.get("source") != "codex-security":
        errors.append("Codex handoff source must be codex-security")
    if payload.get("implementation_allowed") is not False:
        errors.append("Codex handoff implementation_allowed must remain false")
    comparison = payload.get("comparison")
    if not isinstance(comparison, dict):
        errors.append("Codex handoff must include the compared evidence snapshots")
    else:
        comparison_result = validate_codex_compare(comparison)
        errors.extend(f"comparison: {error}" for error in comparison_result["errors"])
        warnings.extend(f"comparison: {warning}" for warning in comparison_result["warnings"])
        if payload.get("comparison_hash") != comparison.get("comparison_hash"):
            errors.append("Codex handoff comparison_hash is not bound to comparison")
        if payload.get("baseline_evidence_hash") != comparison.get("baseline_hash"):
            errors.append("Codex handoff baseline_evidence_hash is not bound to comparison")
        if payload.get("current_evidence_hash") != comparison.get("current_hash"):
            errors.append("Codex handoff current_evidence_hash is not bound to comparison")
        input_hashes = payload.get("input_hashes")
        if not isinstance(input_hashes, Mapping):
            errors.append("Codex handoff input_hashes are required")
        else:
            expected_input_hashes = {
                "baseline": comparison.get("baseline_hash"),
                "current": comparison.get("current_hash"),
                "comparison": comparison.get("comparison_hash"),
            }
            if canonical_json(input_hashes) != canonical_json(expected_input_hashes):
                errors.append("Codex handoff input_hashes are not bound to comparison")
        comparison_matches = comparison.get("matches")
        if isinstance(comparison_matches, list):
            expected_status = _handoff_status(comparison_matches, comparison)
            expected_findings = [
                match
                for match in comparison_matches
                if isinstance(match, Mapping)
                and match.get("status") in {"new", "present", "unknown"}
            ]
            if payload.get("status") != expected_status:
                errors.append("Codex handoff status is inconsistent with comparison matches")
            if canonical_json(payload.get("findings")) != canonical_json(expected_findings):
                errors.append("Codex handoff findings are not bound to comparison matches")
            if canonical_json(payload.get("summary")) != canonical_json(comparison.get("summary")):
                errors.append("Codex handoff summary is not bound to comparison")
            if canonical_json(payload.get("coverage")) != canonical_json(
                comparison.get("coverage")
            ):
                errors.append("Codex handoff coverage is not bound to comparison")
    if isinstance(payload.get("handoff_hash"), str):
        expected = canonical_hash(payload, exclude=("handoff_hash",))
        if payload["handoff_hash"] != expected:
            errors.append("Codex handoff handoff_hash does not match the artifact contents")
    else:
        errors.append("Codex handoff handoff_hash is required")
    return _validation_result(payload, errors=errors, warnings=warnings)


def validate_codex_document(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch validation for evidence, comparison, or handoff artifacts."""

    schema = payload.get("schema") if isinstance(payload, Mapping) else None
    if schema == CODEX_SECURITY_EVIDENCE_SCHEMA:
        return validate_codex_evidence(payload)
    if schema == CODEX_SECURITY_COMPARE_SCHEMA:
        return validate_codex_compare(payload)
    if schema == CODEX_SECURITY_HANDOFF_SCHEMA:
        return validate_codex_handoff(payload)
    return _validation_result(payload, errors=[f"unsupported Codex document schema: {schema}"])


def security_result(
    *,
    operation: str,
    status: str,
    artifact: Mapping[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a stable command result without changing the underlying artifact."""

    result: dict[str, Any] = {
        "schema": CODEX_SECURITY_RESULT_SCHEMA,
        "operation": operation,
        "status": status,
        "implementation_allowed": False,
    }
    if artifact is not None:
        result["artifact_schema"] = artifact.get("schema")
        result["artifact"] = dict(artifact)
        for key in ("evidence_hash", "comparison_hash", "handoff_hash", "summary", "coverage"):
            if key in artifact:
                result[key] = artifact[key]
    result.update(extra)
    return result


def render_codex_handoff_markdown(handoff: Mapping[str, Any]) -> str:
    """Render a concise human handoff while retaining hashes in the artifact."""

    summary = handoff.get("summary", {})
    lines = [
        "# Codex Security handoff",
        "",
        f"- Status: `{handoff.get('status', 'unknown')}`",
        f"- Baseline evidence hash: `{handoff.get('baseline_evidence_hash', '')}`",
        f"- Current evidence hash: `{handoff.get('current_evidence_hash', '')}`",
        f"- Comparison hash: `{handoff.get('comparison_hash', '')}`",
        f"- Handoff hash: `{handoff.get('handoff_hash', '')}`",
        f"- Follow-up coverage complete: `{summary.get('follow_up_coverage_complete', False)}`",
        "",
        "## Findings",
        "",
    ]
    findings = handoff.get("findings", [])
    if not findings:
        lines.append("No actionable findings.")
    else:
        for finding in findings:
            lines.append(
                "- "
                f"`{finding.get('status', 'unknown')}` "
                f"`{finding.get('match_key', '')}`: {finding.get('reason', '')}"
            )
    return "\n".join(lines) + "\n"


def _handoff_status(
    matches: Sequence[Mapping[str, Any]], comparison: Mapping[str, Any] | None = None
) -> str:
    if comparison is not None and not _comparison_coverage_complete(comparison):
        return "unknown"
    if any(match.get("status") == "unknown" for match in matches):
        return "unknown"
    if any(match.get("status") in {"new", "present"} for match in matches):
        return "review-required"
    return "clean"


def _comparison_coverage_complete(comparison: Mapping[str, Any]) -> bool:
    coverage = comparison.get("coverage")
    summary = comparison.get("summary")
    return bool(
        isinstance(coverage, Mapping)
        and coverage.get("complete") is True
        and isinstance(summary, Mapping)
        and summary.get("follow_up_coverage_complete") is True
    )
