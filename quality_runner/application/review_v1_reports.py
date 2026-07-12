from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from quality_runner.core.review_contracts import (
    AdapterStatus,
    ReviewBreadth,
    ReviewClassification,
    ReviewConfidence,
    ReviewFinding,
    ReviewMode,
    ReviewReport,
    ReviewScope,
    ReviewSections,
    ReviewSeverity,
    SeverityCounts,
)

REVIEW_REPORT_SCHEMA = "quality-runner-review-report-v0.1"

_MODES = ("task", "blind", "combined")
_SCOPES = ("task", "project")
_BREADTHS = ("focused", "related", "full")
_ADAPTER_STATUSES = (
    "review-complete",
    "review-not-run",
    "malformed-output",
    "permission-denied",
)
_SEVERITIES = ("critical", "high", "medium", "low")
_CLASSIFICATIONS = ("confirmed", "suspected", "not-enough-evidence", "known-accepted")
_CONFIDENCES = ("high", "medium", "low")
_FINDING_SECTION_KEYS = (
    "missed_requirements",
    "confirmed_issues",
    "suspected_issues",
    "not_enough_evidence",
    "project_consistency_risks",
    "regression_risks",
    "known_accepted_issues",
)
_REPORT_KEYS = frozenset(
    {
        "schema",
        "run_id",
        "mode",
        "scope",
        "breadth",
        "adapter_status",
        "task_provenance",
        "summary",
        "next_action",
        "severity_counts",
        "evidence_used",
        "evidence_unavailable",
        "exclusions",
        "sections",
        "findings",
    }
)
_SEVERITY_COUNT_KEYS = frozenset(_SEVERITIES)
_SECTION_KEYS = frozenset(
    (*_FINDING_SECTION_KEYS, "suggested_fixes", "agent_handoff_prompts", "remaining_uncertainty")
)
_FINDING_KEYS = frozenset(
    {
        "id",
        "fingerprint",
        "severity",
        "classification",
        "confidence",
        "summary",
        "why_it_matters",
        "location",
        "evidence",
        "recommended_fix",
        "agent_prompt",
        "human_confirmation_required",
        "status",
    }
)


def review_report_to_v1(report: ReviewReport) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": report["schema"],
        "run_id": report["run_id"],
        "mode": report["mode"],
        "scope": report["scope"],
        "breadth": report["breadth"],
        "adapter_status": report["adapter_status"],
        "task_provenance": report["task_provenance"],
        "summary": report["summary"],
        "severity_counts": dict(report["severity_counts"]),
        "evidence_used": list(report["evidence_used"]),
        "evidence_unavailable": list(report["evidence_unavailable"]),
        "exclusions": list(report["exclusions"]),
        "sections": _sections_to_v1(report["sections"]),
        "findings": [_finding_to_v1(item) for item in report["findings"]],
    }
    if "next_action" in report:
        payload["next_action"] = report["next_action"]
    return payload


def review_report_from_v1(payload: Mapping[str, object]) -> ReviewReport:
    _reject_extra_keys(payload, _REPORT_KEYS, "review report")
    _expect_schema(payload, REVIEW_REPORT_SCHEMA)
    if "task_provenance" not in payload:
        raise ValueError("task_provenance must be a string or null")
    task_provenance = payload.get("task_provenance")
    if task_provenance is not None and not isinstance(task_provenance, str):
        raise ValueError("task_provenance must be a string or null")
    report: ReviewReport = {
        "schema": _string(payload, "schema"),
        "run_id": _string(payload, "run_id"),
        "mode": _mode(payload, "mode"),
        "scope": _scope(payload, "scope"),
        "breadth": _breadth(payload, "breadth"),
        "adapter_status": _adapter_status(payload, "adapter_status"),
        "task_provenance": task_provenance,
        "summary": _string(payload, "summary"),
        "severity_counts": _severity_counts(_object(payload, "severity_counts")),
        "evidence_used": _string_list(payload, "evidence_used"),
        "evidence_unavailable": _string_list(payload, "evidence_unavailable"),
        "exclusions": _string_list(payload, "exclusions"),
        "sections": _sections_from_v1(_object(payload, "sections")),
        "findings": _findings(_sequence(payload, "findings")),
    }
    if "next_action" in payload:
        report["next_action"] = _string(payload, "next_action")
    return report


def _finding_to_v1(finding: ReviewFinding) -> dict[str, object]:
    return {
        "id": finding["id"],
        "fingerprint": finding["fingerprint"],
        "severity": finding["severity"],
        "classification": finding["classification"],
        "confidence": finding["confidence"],
        "summary": finding["summary"],
        "why_it_matters": finding["why_it_matters"],
        "location": list(finding["location"]),
        "evidence": list(finding["evidence"]),
        "recommended_fix": finding["recommended_fix"],
        "agent_prompt": finding["agent_prompt"],
        "human_confirmation_required": finding["human_confirmation_required"],
        "status": finding["status"],
    }


def _sections_to_v1(sections: ReviewSections) -> dict[str, object]:
    payload: dict[str, object] = {
        key: [_finding_to_v1(item) for item in sections[key]] for key in _FINDING_SECTION_KEYS
    }
    payload["suggested_fixes"] = list(sections["suggested_fixes"])
    payload["agent_handoff_prompts"] = list(sections["agent_handoff_prompts"])
    payload["remaining_uncertainty"] = list(sections["remaining_uncertainty"])
    return payload


def _severity_counts(payload: Mapping[str, object]) -> SeverityCounts:
    _reject_extra_keys(payload, _SEVERITY_COUNT_KEYS, "severity counts")
    values = {key: payload.get(key) for key in _SEVERITIES}
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in values.values()
    ):
        raise ValueError("severity counts must be non-negative integers")
    return cast(SeverityCounts, values)


def _findings(values: Sequence[object]) -> list[ReviewFinding]:
    return [_finding_from_v1(_object_value(value, "findings")) for value in values]


def _finding_from_v1(payload: Mapping[str, object]) -> ReviewFinding:
    _reject_extra_keys(payload, _FINDING_KEYS, "finding")
    confirmation = payload.get("human_confirmation_required")
    if not isinstance(confirmation, bool):
        raise ValueError("finding human_confirmation_required must be a boolean")
    return {
        "id": _string(payload, "id"),
        "fingerprint": _string(payload, "fingerprint"),
        "severity": _severity(payload, "severity"),
        "classification": _classification(payload, "classification"),
        "confidence": _confidence(payload, "confidence"),
        "summary": _string(payload, "summary"),
        "why_it_matters": _string(payload, "why_it_matters"),
        "location": _string_list(payload, "location", nonempty_values=True),
        "evidence": _string_list(payload, "evidence", nonempty_values=True),
        "recommended_fix": _string(payload, "recommended_fix"),
        "agent_prompt": _string(payload, "agent_prompt"),
        "human_confirmation_required": confirmation,
        "status": _string(payload, "status"),
    }


def _sections_from_v1(payload: Mapping[str, object]) -> ReviewSections:
    _reject_extra_keys(payload, _SECTION_KEYS, "sections")
    return {
        "missed_requirements": _findings(_sequence(payload, "missed_requirements")),
        "confirmed_issues": _findings(_sequence(payload, "confirmed_issues")),
        "suspected_issues": _findings(_sequence(payload, "suspected_issues")),
        "not_enough_evidence": _findings(_sequence(payload, "not_enough_evidence")),
        "project_consistency_risks": _findings(_sequence(payload, "project_consistency_risks")),
        "regression_risks": _findings(_sequence(payload, "regression_risks")),
        "known_accepted_issues": _findings(_sequence(payload, "known_accepted_issues")),
        "suggested_fixes": _string_list(payload, "suggested_fixes"),
        "agent_handoff_prompts": _string_list(payload, "agent_handoff_prompts"),
        "remaining_uncertainty": _string_list(payload, "remaining_uncertainty"),
    }


def _expect_schema(payload: Mapping[str, object], expected: str) -> None:
    if payload.get("schema") != expected:
        raise ValueError(f"expected schema {expected}")


def _reject_extra_keys(payload: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    extra = sorted(set(payload) - allowed)
    if extra:
        raise ValueError(f"{label} contains unsupported fields: {', '.join(extra)}")


def _object(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    return _object_value(payload.get(key), key)


def _object_value(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(payload: Mapping[str, object], key: str) -> Sequence[object]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{key} must be an array")
    return value


def _string(payload: Mapping[str, object], key: str) -> str:
    value = _text(payload, key)
    if not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _string_list(
    payload: Mapping[str, object], key: str, *, nonempty_values: bool = False
) -> list[str]:
    values = _sequence(payload, key)
    if not all(isinstance(value, str) and (not nonempty_values or bool(value)) for value in values):
        raise ValueError(f"{key} must contain strings")
    return list(cast(Sequence[str], values))


def _mode(payload: Mapping[str, object], key: str) -> ReviewMode:
    value = _string(payload, key)
    if value not in _MODES:
        raise ValueError(f"invalid mode: {value}")
    return cast(ReviewMode, value)


def _scope(payload: Mapping[str, object], key: str) -> ReviewScope:
    value = _string(payload, key)
    if value not in _SCOPES:
        raise ValueError(f"invalid scope: {value}")
    return cast(ReviewScope, value)


def _breadth(payload: Mapping[str, object], key: str) -> ReviewBreadth:
    value = _string(payload, key)
    if value not in _BREADTHS:
        raise ValueError(f"invalid breadth: {value}")
    return cast(ReviewBreadth, value)


def _adapter_status(payload: Mapping[str, object], key: str) -> AdapterStatus:
    value = _string(payload, key)
    if value not in _ADAPTER_STATUSES:
        raise ValueError(f"invalid adapter status: {value}")
    return cast(AdapterStatus, value)


def _severity(payload: Mapping[str, object], key: str) -> ReviewSeverity:
    value = _string(payload, key)
    if value not in _SEVERITIES:
        raise ValueError(f"invalid finding severity: {value}")
    return cast(ReviewSeverity, value)


def _classification(payload: Mapping[str, object], key: str) -> ReviewClassification:
    value = _string(payload, key)
    if value not in _CLASSIFICATIONS:
        raise ValueError(f"invalid finding classification: {value}")
    return cast(ReviewClassification, value)


def _confidence(payload: Mapping[str, object], key: str) -> ReviewConfidence:
    value = _string(payload, key)
    if value not in _CONFIDENCES:
        raise ValueError(f"invalid finding confidence: {value}")
    return cast(ReviewConfidence, value)
