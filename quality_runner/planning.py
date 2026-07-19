from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.adoption import build_adoption_stage, handoff_adoption_stage, stopping_criteria
from quality_runner.core.audit_contracts import TextScanScope
from quality_runner.evidence_excerpts import SourceExcerptReader
from quality_runner.handoff_gate_suggestions import (
    gate_severity,
    suggested_gate_command,
)
from quality_runner.handoff_gate_summary import (
    build_gate_verification_summary,
    gate_blocker_slice,
    gate_handoff_status,
)
from quality_runner.handoff_markdown import render_handoff_markdown as render_handoff_markdown
from quality_runner.handoff_status import apply_skill_review_status, handoff_status
from quality_runner.lifecycle_status import compute_lifecycle_status
from quality_runner.planning_markdown import render_plan_markdown as _render_plan_markdown
from quality_runner.planning_slices import finding_sort_key, slice_for_finding, slice_sort_key
from quality_runner.remediation_clusters import structural_cluster_slices
from quality_runner.remediation_domains import (
    annotate_remediation_slices,
    build_phase_candidates,
    phase_candidate_summaries,
)
from quality_runner.remediation_wiring import wiring_decision_slices
from quality_runner.runner_checks import runner_provided_checks
from quality_runner.schema_constants import AGENT_HANDOFF_SCHEMA, REMEDIATION_PLAN_SCHEMA
from quality_runner.security.handoff import security_review_handoff
from quality_runner.slice_enrichment import enrich_remediation_slices

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def render_plan_markdown(plan: dict[str, Any]) -> str:
    return _render_plan_markdown(plan)


def build_remediation_plan(
    *,
    audit_report: dict[str, Any],
    capability_map: dict[str, Any],
    code_quality_scan: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    git_state: dict[str, Any] | None = None,
    text_scan_scope: TextScanScope | None = None,
) -> dict[str, Any]:
    all_findings = sorted(_findings(audit_report), key=finding_sort_key)
    remediation_findings = [
        finding
        for finding in all_findings
        if not str(finding.get("category", "")).startswith("security:agent-review")
    ]
    security_review_findings = [
        finding
        for finding in all_findings
        if str(finding.get("category", "")).startswith("security:agent-review")
    ]
    wiring_slices = wiring_decision_slices(code_quality_scan)
    structural_slices = structural_cluster_slices(
        code_quality_scan,
        excluded_categories={"integrate"} if wiring_slices else set(),
    )
    slices = [
        *[
            slice_for_finding(finding)
            for finding in remediation_findings
            if _include_finding_slice(
                finding,
                structural_slices=structural_slices,
                wiring_slices=wiring_slices,
            )
        ],
        *structural_slices,
        *wiring_slices,
    ]
    security_review_slices = [slice_for_finding(finding) for finding in security_review_findings]
    run_id = _string_or_none(audit_report.get("run_id"))
    excerpt_reader = (
        SourceExcerptReader(repo_root, source_scope=text_scan_scope)
        if repo_root is not None
        else None
    )
    slices = enrich_remediation_slices(
        slices,
        repo_root=repo_root,
        git_state=git_state,
        code_quality_scan=code_quality_scan,
        run_id=run_id,
        excerpt_reader=excerpt_reader,
    )
    security_review_slices = enrich_remediation_slices(
        security_review_slices,
        repo_root=repo_root,
        git_state=git_state,
        code_quality_scan=code_quality_scan,
        run_id=run_id,
        excerpt_reader=excerpt_reader,
    )
    slices = sorted(slices, key=slice_sort_key)
    slices = annotate_remediation_slices(slices)
    security_review_slices = annotate_remediation_slices(security_review_slices)
    phase_candidates = build_phase_candidates(
        slices,
        security_review_slices=security_review_slices,
    )
    adoption_stage = build_adoption_stage(
        findings=remediation_findings,
        missing_gates=_missing_repo_owned_gates(capability_map),
        warnings=_warnings(capability_map),
    )

    return {
        "schema": REMEDIATION_PLAN_SCHEMA,
        "run_id": _string_or_none(audit_report.get("run_id")),
        "profile": _string_or_none(audit_report.get("profile")),
        "implementation_allowed": False,
        "adoption_stage": adoption_stage,
        "stopping_criteria": stopping_criteria(adoption_stage),
        "planning_mode": "domain",
        "phase_candidate_count": len(phase_candidates),
        "leaf_slice_count": len(slices) + len(security_review_slices),
        "phase_candidates": phase_candidates,
        "slices": slices,
        **({"security_review_slices": security_review_slices} if security_review_slices else {}),
        "warnings": _warnings(capability_map),
    }


def build_agent_handoff(
    *,
    audit_report: dict[str, Any],
    remediation_plan: dict[str, Any],
    artifact_paths: dict[str, str],
    capability_map: dict[str, Any] | None = None,
    gate_verification: dict[str, Any] | None = None,
    security_scan: dict[str, Any] | None = None,
    intent: dict[str, Any] | None = None,
    intent_docs: list[dict[str, str]] | None = None,
    lifecycle_status: str | None = None,
    repo_scan: dict[str, Any] | None = None,
    skill_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    missing_gates = _missing_repo_owned_gates(capability_map)
    gate_summary = build_gate_verification_summary(
        gate_verification=gate_verification,
        finding_count=len(_findings(audit_report)),
        missing_capability_count=len(missing_gates),
    )
    status = gate_handoff_status(gate_summary) or handoff_status(
        remediation_plan=remediation_plan,
        capability_map=capability_map,
        missing_repo_owned_gates=missing_gates,
    )
    status = apply_skill_review_status(status, skill_review)
    next_slice = (
        gate_blocker_slice(gate_summary)
        or _author_decision_slice(remediation_plan)
        or _next_slice(remediation_plan)
    )
    phase_candidates = phase_candidate_summaries(_phase_candidates(remediation_plan))
    adoption_stage = handoff_adoption_stage(remediation_plan)
    resolved_lifecycle = lifecycle_status or compute_lifecycle_status(
        summary_status=str(gate_summary.get("status") if gate_summary else status),
        handoff_status=status,
        gate_verification=gate_verification or {},
        audit=audit_report,
        repo_scan=repo_scan,
    )
    return {
        "schema": AGENT_HANDOFF_SCHEMA,
        "run_id": _string_or_none(audit_report.get("run_id")),
        "status": status,
        "implementation_allowed": False,
        "artifact_paths": artifact_paths,
        "warnings": _warnings(remediation_plan),
        "finding_ids": [finding["id"] for finding in _findings(audit_report)],
        "slice_ids": [slice_item["id"] for slice_item in _slices(remediation_plan)],
        "phase_candidates": phase_candidates,
        "next_phase_candidate": phase_candidates[0] if phase_candidates else None,
        "missing_repo_owned_gates": missing_gates,
        "runner_provided_checks": runner_provided_checks(_findings(audit_report)),
        "adoption_stage": adoption_stage,
        "stopping_criteria": stopping_criteria(adoption_stage),
        **_optional_value("gate_verification", gate_summary),
        **_optional_value(
            "security_review", security_review_handoff(security_scan, capability_map)
        ),
        **_optional_value("intent", intent),
        **_optional_value("intent_docs", intent_docs or _intent_docs_from_scan(repo_scan)),
        **_optional_value("lifecycle_status", resolved_lifecycle),
        **_optional_value("skill_review", skill_review),
        "next_slice": next_slice,
        "verification_gates": _slice_verification_gates(next_slice),
    }


def _slice_for_finding(finding: dict[str, Any]) -> dict[str, Any]:
    return slice_for_finding(finding)


def _include_finding_slice(
    finding: dict[str, Any],
    *,
    structural_slices: list[dict[str, Any]],
    wiring_slices: list[dict[str, Any]],
) -> bool:
    category = str(finding.get("category") or "")
    if not category.startswith("structural:"):
        return True
    if category == "structural:integrate" and wiring_slices:
        return False
    return structural_slices == []


def _missing_repo_owned_gates(capability_map: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(capability_map, dict):
        return []
    missing = capability_map.get("missing")
    if not isinstance(missing, list):
        return []

    gates: list[dict[str, str]] = []
    for capability in missing:
        if not isinstance(capability, dict):
            continue
        capability_id = capability.get("id")
        reason = capability.get("reason")
        language = capability.get("language")
        required_by = capability.get("required_by")
        if not isinstance(capability_id, str) or not capability_id:
            continue
        if capability_id.startswith("security_"):
            continue
        gates.append(
            {
                "id": capability_id,
                "severity": gate_severity(capability_id),
                "reason": reason if isinstance(reason, str) and reason else "gate was not found",
                "suggested_command": suggested_gate_command(capability_id, language),
                **_optional_string("required_by", required_by),
            }
        )
    return gates


def _optional_string(key: str, value: object) -> dict[str, str]:
    if isinstance(value, str) and value:
        return {key: value}
    return {}


def _optional_value(key: str, value: object) -> dict[str, object]:
    if value is None:
        return {}
    return {key: value}


def _findings(audit_report: dict[str, Any]) -> list[dict[str, Any]]:
    findings = audit_report.get("findings")
    if not isinstance(findings, list):
        return []

    normalized: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_id = finding.get("id")
        severity = finding.get("severity")
        category = finding.get("category")
        summary = finding.get("summary")
        recommended_fix = finding.get("recommended_fix")
        verification = finding.get("verification")
        score = finding.get("score")
        if (
            isinstance(finding_id, str)
            and finding_id
            and isinstance(severity, str)
            and severity
            and isinstance(category, str)
            and category
            and isinstance(summary, str)
            and summary
            and isinstance(recommended_fix, str)
            and recommended_fix
            and isinstance(verification, list)
            and all(isinstance(item, str) and item for item in verification)
        ):
            normalized.append(
                {
                    "id": finding_id,
                    "severity": severity,
                    "category": category,
                    "summary": summary,
                    "recommended_fix": recommended_fix,
                    "verification": verification,
                    "score": score if isinstance(score, int) else _default_score(severity),
                    **_optional_actionability(finding),
                    **_optional_disposition(finding),
                }
            )
    return normalized


def _slices(plan: dict[str, Any]) -> list[dict[str, str]]:
    slices = plan.get("slices")
    if not isinstance(slices, list):
        return []
    return [
        {"id": slice_item["id"]}
        for slice_item in slices
        if isinstance(slice_item, dict)
        and isinstance(slice_item.get("id"), str)
        and slice_item["id"]
    ]


def _phase_candidates(plan: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = plan.get("phase_candidates")
    if not isinstance(candidates, list):
        return []
    return [candidate for candidate in candidates if isinstance(candidate, dict)]


def _next_slice(plan: dict[str, Any]) -> dict[str, Any] | None:
    slices = plan.get("slices")
    if not isinstance(slices, list) or not slices:
        return None
    first = slices[0]
    if not isinstance(first, dict):
        return None
    return _copy_next_slice(first)


def _author_decision_slice(plan: dict[str, Any]) -> dict[str, Any] | None:
    slices = plan.get("slices")
    if not isinstance(slices, list):
        return None
    for slice_item in slices:
        if not isinstance(slice_item, dict):
            continue
        if slice_item.get("disposition_required") is True or _slice_needs_author_decision(
            slice_item
        ):
            return _copy_next_slice(slice_item)
    return None


def _copy_next_slice(first: dict[str, Any]) -> dict[str, Any] | None:
    try:
        next_slice = {
            "id": first["id"],
            "title": first["title"],
            "priority": first["priority"],
            "findings": list(first["findings"]),
            "actions": list(first["actions"]),
            "verification_gates": list(first["verification_gates"]),
        }
    except (KeyError, TypeError):
        return None
    if first.get("implementation_allowed") is False:
        next_slice["implementation_allowed"] = False
    if first.get("disposition_required") is True:
        next_slice["disposition_required"] = True
    if isinstance(first.get("action_groups"), list):
        next_slice["action_groups"] = list(first["action_groups"])
    if isinstance(first.get("score"), int):
        next_slice["score"] = first["score"]
    for field in (
        "impact",
        "effort",
        "fix_risk",
        "confidence",
        "why_now",
        "leverage",
        "planned_at",
        "drift_check",
        "scope",
        "stop_conditions",
        "verification_mode",
        "verification_requirements",
    ):
        if field in first:
            next_slice[field] = first[field]
    return next_slice


def _slice_needs_author_decision(slice_item: dict[str, Any]) -> bool:
    findings = slice_item.get("findings")
    if not isinstance(findings, list):
        return False
    return any(
        isinstance(finding, dict) and finding.get("actionability") == "needs-author-decision"
        for finding in findings
    )


def _slice_verification_gates(slice_item: dict[str, Any] | None) -> list[str]:
    if slice_item is None:
        return []
    verification_gates = slice_item.get("verification_gates")
    if not isinstance(verification_gates, list):
        return []
    return [gate for gate in verification_gates if isinstance(gate, str)]


def _warnings(payload: dict[str, Any]) -> list[dict[str, str]]:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        return []

    normalized: list[dict[str, str]] = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code")
        message = warning.get("message")
        path = warning.get("path")
        if isinstance(code, str) and isinstance(message, str) and isinstance(path, str):
            normalized.append({"code": code, "message": message, "path": path})
    return normalized


def _optional_actionability(finding: dict[str, Any]) -> dict[str, str]:
    actionability = finding.get("actionability")
    rationale = finding.get("actionability_rationale")
    if not isinstance(actionability, str) or not actionability:
        return {}
    payload: dict[str, str] = {"actionability": actionability}
    if isinstance(rationale, str) and rationale:
        payload["actionability_rationale"] = rationale
    return payload


def _optional_disposition(finding: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in (
        "disposition_class",
        "disposition_group",
        "disposition_required",
        "owner_role",
        "disposition_rationale",
    ):
        if key in finding and finding[key] is not None:
            payload[key] = finding[key]
    return payload


def _default_score(severity: str) -> int:
    return {"critical": 1000, "blocker": 900}.get(severity, 0)


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _intent_docs_from_scan(repo_scan: dict[str, Any] | None) -> list[dict[str, str]] | None:
    if not isinstance(repo_scan, dict):
        return None
    intent_docs = repo_scan.get("intent_docs")
    if not isinstance(intent_docs, list):
        return None
    normalized: list[dict[str, str]] = []
    for doc in intent_docs:
        if not isinstance(doc, dict):
            continue
        doc_type = doc.get("type")
        path = doc.get("path")
        if isinstance(doc_type, str) and isinstance(path, str) and doc_type and path:
            normalized.append({"type": doc_type, "path": path})
    return normalized or None
