from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from quality_runner.application.review_v1_serializers import REVIEW_REPORT_SCHEMA
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

SEVERITIES = ("critical", "high", "medium", "low")
CLASSIFICATIONS = ("confirmed", "suspected", "not-enough-evidence", "known-accepted")
CONFIDENCES = ("high", "medium", "low")
ADAPTER_STATUSES = ("review-complete", "review-not-run", "malformed-output", "permission-denied")
NO_ISSUE_CAVEAT = "No major issues found from available evidence, but this does not prove the feature works end-to-end."
PACKET_READY_SUMMARY = "Review packet ready: no review was run. Send the packet to a reviewer, then rerun with --adapter-output."
INCOMPLETE_REVIEW_SUMMARY = (
    "Review did not complete; no finding conclusion can be drawn from this result."
)


def build_review_report(
    *,
    run_id: str,
    mode: str,
    scope: str,
    breadth: str,
    findings: Sequence[Mapping[str, object]],
    evidence_used: Sequence[str],
    evidence_unavailable: Sequence[str],
    exclusions: Sequence[str],
    adapter_status: str,
    task_provenance: str | None,
) -> ReviewReport:
    if mode not in {"task", "blind", "combined"}:
        raise ValueError(f"invalid review mode: {mode}")
    if scope not in {"task", "project"}:
        raise ValueError(f"invalid review scope: {scope}")
    if breadth not in {"focused", "related", "full"}:
        raise ValueError(f"invalid review breadth: {breadth}")
    if adapter_status not in ADAPTER_STATUSES:
        raise ValueError(f"invalid adapter status: {adapter_status}")
    resolved_mode = cast(ReviewMode, mode)
    resolved_scope = cast(ReviewScope, scope)
    resolved_breadth = cast(ReviewBreadth, breadth)
    resolved_status = cast(AdapterStatus, adapter_status)
    if resolved_mode in {"task", "combined"} and not task_provenance:
        raise ValueError("task provenance is required for task and combined reports")
    normalized = [_normalize_finding(finding) for finding in findings]
    if resolved_status != "review-complete" and normalized:
        raise ValueError("findings require a review-complete adapter status")
    counts: SeverityCounts = {
        "critical": sum(item["severity"] == "critical" for item in normalized),
        "high": sum(item["severity"] == "high" for item in normalized),
        "medium": sum(item["severity"] == "medium" for item in normalized),
        "low": sum(item["severity"] == "low" for item in normalized),
    }
    summary = (
        f"Review complete: {counts['critical']} critical, {counts['high']} high, "
        f"{counts['medium']} medium issues found."
    )
    if not normalized:
        if resolved_status == "review-complete":
            summary = NO_ISSUE_CAVEAT
        elif resolved_status == "review-not-run":
            summary = PACKET_READY_SUMMARY
        else:
            summary = INCOMPLETE_REVIEW_SUMMARY
    return {
        "schema": REVIEW_REPORT_SCHEMA,
        "run_id": run_id,
        "mode": resolved_mode,
        "scope": resolved_scope,
        "breadth": resolved_breadth,
        "adapter_status": resolved_status,
        "task_provenance": task_provenance,
        "summary": summary,
        "severity_counts": counts,
        "evidence_used": _clean_strings(evidence_used),
        "evidence_unavailable": _clean_strings(evidence_unavailable),
        "exclusions": _clean_strings(exclusions),
        "sections": _sections(normalized, mode=resolved_mode),
        "findings": normalized,
    }


def _normalize_finding(finding: Mapping[str, object]) -> ReviewFinding:
    required_text = (
        "id",
        "fingerprint",
        "severity",
        "classification",
        "confidence",
        "summary",
        "why_it_matters",
        "recommended_fix",
        "agent_prompt",
        "status",
    )
    values: dict[str, str] = {}
    for field in required_text:
        value = finding.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"finding requires {field}")
        values[field] = value.strip()
    severity = values["severity"]
    classification = values["classification"]
    confidence = values["confidence"]
    if severity not in SEVERITIES:
        raise ValueError(f"invalid finding severity: {severity}")
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"invalid finding classification: {classification}")
    if confidence not in CONFIDENCES:
        raise ValueError(f"invalid finding confidence: {confidence}")
    confirmation = finding.get("human_confirmation_required")
    if not isinstance(confirmation, bool):
        raise ValueError("finding requires human_confirmation_required")
    return {
        "id": values["id"],
        "fingerprint": values["fingerprint"],
        "severity": cast(ReviewSeverity, severity),
        "classification": cast(ReviewClassification, classification),
        "confidence": cast(ReviewConfidence, confidence),
        "summary": values["summary"],
        "why_it_matters": values["why_it_matters"],
        "recommended_fix": values["recommended_fix"],
        "agent_prompt": values["agent_prompt"],
        "status": values["status"],
        "location": _string_list(finding.get("location"), "location"),
        "evidence": _string_list(finding.get("evidence"), "evidence"),
        "human_confirmation_required": confirmation,
    }


def _sections(findings: Sequence[ReviewFinding], *, mode: ReviewMode) -> ReviewSections:
    sections: ReviewSections = {
        "missed_requirements": [],
        "confirmed_issues": [],
        "suspected_issues": [],
        "not_enough_evidence": [],
        "project_consistency_risks": [],
        "regression_risks": [],
        "known_accepted_issues": [],
        "suggested_fixes": [],
        "agent_handoff_prompts": [],
        "remaining_uncertainty": [],
    }
    for finding in findings:
        classification = finding["classification"]
        if classification == "confirmed":
            sections["confirmed_issues"].append(finding)
        elif classification == "suspected":
            sections["suspected_issues"].append(finding)
        elif classification == "not-enough-evidence":
            sections["not_enough_evidence"].append(finding)
        elif classification == "known-accepted":
            sections["known_accepted_issues"].append(finding)
        sections["suggested_fixes"].append(finding["recommended_fix"])
        sections["agent_handoff_prompts"].append(finding["agent_prompt"])
        if finding["confidence"] != "high" or finding["human_confirmation_required"]:
            sections["remaining_uncertainty"].append(finding["id"])
    if mode == "blind":
        sections["missed_requirements"] = []
    return sections


def _string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"finding requires non-empty string list for {field}")
    return [item.strip() for item in value]


def _clean_strings(values: Sequence[str]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()})
