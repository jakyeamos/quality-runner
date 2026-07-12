from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypedDict, cast

from quality_runner.review_types import ReviewBreadth, ReviewMode, ReviewScope

SEVERITIES = ("critical", "high", "medium", "low")
CLASSIFICATIONS = ("confirmed", "suspected", "not-enough-evidence", "known-accepted")
CONFIDENCES = ("high", "medium", "low")
ADAPTER_STATUSES = ("review-complete", "review-not-run", "malformed-output", "permission-denied")
NO_ISSUE_CAVEAT = "No major issues found from available evidence, but this does not prove the feature works end-to-end."
PACKET_READY_SUMMARY = "Review packet ready: no review was run. Send the packet to a reviewer, then rerun with --adapter-output."
INCOMPLETE_REVIEW_SUMMARY = (
    "Review did not complete; no finding conclusion can be drawn from this result."
)


class ReviewFinding(TypedDict):
    id: str
    fingerprint: str
    severity: str
    classification: str
    confidence: str
    summary: str
    why_it_matters: str
    location: list[str]
    evidence: list[str]
    recommended_fix: str
    agent_prompt: str
    human_confirmation_required: bool
    status: str


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
) -> dict[str, object]:
    if mode not in {"task", "blind", "combined"}:
        raise ValueError(f"invalid review mode: {mode}")
    if scope not in {"task", "project"}:
        raise ValueError(f"invalid review scope: {scope}")
    if breadth not in {"focused", "related", "full"}:
        raise ValueError(f"invalid review breadth: {breadth}")
    if adapter_status not in ADAPTER_STATUSES:
        raise ValueError(f"invalid adapter status: {adapter_status}")
    if mode in {"task", "combined"} and not task_provenance:
        raise ValueError("task provenance is required for task and combined reports")
    normalized = [_normalize_finding(finding) for finding in findings]
    if adapter_status != "review-complete" and normalized:
        raise ValueError("findings require a review-complete adapter status")
    counts = {
        severity: sum(item["severity"] == severity for item in normalized)
        for severity in SEVERITIES
    }
    summary = (
        f"Review complete: {counts['critical']} critical, {counts['high']} high, "
        f"{counts['medium']} medium issues found."
    )
    if not normalized:
        if adapter_status == "review-complete":
            summary = NO_ISSUE_CAVEAT
        elif adapter_status == "review-not-run":
            summary = PACKET_READY_SUMMARY
        else:
            summary = INCOMPLETE_REVIEW_SUMMARY
    sections = _sections(normalized, mode=mode)
    return {
        "schema": "quality-runner-review-report-v0.1",
        "run_id": run_id,
        "mode": cast(ReviewMode, mode),
        "scope": cast(ReviewScope, scope),
        "breadth": cast(ReviewBreadth, breadth),
        "adapter_status": adapter_status,
        "task_provenance": task_provenance,
        "summary": summary,
        "severity_counts": counts,
        "evidence_used": _clean_strings(evidence_used),
        "evidence_unavailable": _clean_strings(evidence_unavailable),
        "exclusions": _clean_strings(exclusions),
        "sections": sections,
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
    if values["severity"] not in SEVERITIES:
        raise ValueError(f"invalid finding severity: {values['severity']}")
    if values["classification"] not in CLASSIFICATIONS:
        raise ValueError(f"invalid finding classification: {values['classification']}")
    if values["confidence"] not in CONFIDENCES:
        raise ValueError(f"invalid finding confidence: {values['confidence']}")
    location = _string_list(finding.get("location"), "location")
    evidence = _string_list(finding.get("evidence"), "evidence")
    confirmation = finding.get("human_confirmation_required")
    if not isinstance(confirmation, bool):
        raise ValueError("finding requires human_confirmation_required")
    return ReviewFinding(
        id=values["id"],
        fingerprint=values["fingerprint"],
        severity=values["severity"],
        classification=values["classification"],
        confidence=values["confidence"],
        summary=values["summary"],
        why_it_matters=values["why_it_matters"],
        recommended_fix=values["recommended_fix"],
        agent_prompt=values["agent_prompt"],
        status=values["status"],
        location=location,
        evidence=evidence,
        human_confirmation_required=confirmation,
    )


def _sections(findings: Sequence[ReviewFinding], *, mode: str) -> dict[str, list[object]]:
    sections: dict[str, list[object]] = {
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
