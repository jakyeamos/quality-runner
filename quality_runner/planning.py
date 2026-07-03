from __future__ import annotations

from typing import Any

from quality_runner.adoption import (
    adoption_stage_markdown,
    build_adoption_stage,
    handoff_adoption_stage,
    stopping_criteria,
)
from quality_runner.findings import AGENT_HANDOFF_SCHEMA, REMEDIATION_PLAN_SCHEMA
from quality_runner.handoff_gate_suggestions import (
    gate_severity,
    suggested_gate_command,
)
from quality_runner.handoff_gate_summary import (
    build_gate_verification_summary,
    gate_blocker_slice,
    gate_handoff_status,
    gate_verification_markdown,
)
from quality_runner.handoff_status import handoff_status

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_remediation_plan(
    *,
    audit_report: dict[str, Any],
    capability_map: dict[str, Any],
) -> dict[str, Any]:
    findings = sorted(_findings(audit_report), key=_finding_sort_key)
    slices = [_slice_for_finding(finding) for finding in findings]
    adoption_stage = build_adoption_stage(
        findings=findings,
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
        "slices": slices,
        "warnings": _warnings(capability_map),
    }


def render_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Quality Runner Remediation Plan",
        "",
        f"- Schema: {plan.get('schema')}",
        f"- Implementation allowed: {str(plan.get('implementation_allowed')).lower()}",
        "",
        "## Adoption Stage",
        "",
        *adoption_stage_markdown(plan.get("adoption_stage")),
        "",
        "## Stopping Criteria",
        "",
        *_markdown_items(plan.get("stopping_criteria")),
        "",
        "## Slices",
        "",
    ]

    slices = plan.get("slices")
    if isinstance(slices, list) and slices:
        for slice_item in slices:
            if not isinstance(slice_item, dict):
                continue
            lines.extend(
                [
                    f"### {slice_item.get('id')}",
                    "",
                    f"- Title: {slice_item.get('title')}",
                    f"- Priority: {slice_item.get('priority')}",
                    "- Findings:",
                    *_finding_markdown_items(slice_item.get("findings")),
                    "- Actions:",
                    *_markdown_items(slice_item.get("actions")),
                    "- Verification:",
                    *_markdown_items(slice_item.get("verification_gates")),
                    "",
                ]
            )
    else:
        lines.extend(["No remediation slices are required.", ""])

    return "\n".join(lines).rstrip() + "\n"


def build_agent_handoff(
    *,
    audit_report: dict[str, Any],
    remediation_plan: dict[str, Any],
    artifact_paths: dict[str, str],
    capability_map: dict[str, Any] | None = None,
    gate_verification: dict[str, Any] | None = None,
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
    next_slice = gate_blocker_slice(gate_summary) or _next_slice(remediation_plan)
    adoption_stage = handoff_adoption_stage(remediation_plan)
    return {
        "schema": AGENT_HANDOFF_SCHEMA,
        "run_id": _string_or_none(audit_report.get("run_id")),
        "status": status,
        "implementation_allowed": False,
        "artifact_paths": artifact_paths,
        "warnings": _warnings(remediation_plan),
        "finding_ids": [finding["id"] for finding in _findings(audit_report)],
        "slice_ids": [slice_item["id"] for slice_item in _slices(remediation_plan)],
        "missing_repo_owned_gates": missing_gates,
        "runner_provided_checks": _runner_provided_checks(audit_report),
        "adoption_stage": adoption_stage,
        "stopping_criteria": stopping_criteria(adoption_stage),
        **_optional_value("gate_verification", gate_summary),
        "next_slice": next_slice,
        "verification_gates": _slice_verification_gates(next_slice),
    }


def render_handoff_markdown(handoff: dict[str, Any]) -> str:
    lines = [
        "# Quality Runner Agent Handoff",
        "",
        f"- Schema: {handoff.get('schema')}",
        f"- Status: {handoff.get('status')}",
        f"- Implementation allowed: {str(handoff.get('implementation_allowed')).lower()}",
        "",
        *(gate_verification_markdown(handoff.get("gate_verification"))),
        "",
        "## Artifacts",
        "",
    ]

    artifact_paths = handoff.get("artifact_paths")
    if isinstance(artifact_paths, dict):
        for name in sorted(artifact_paths):
            value = artifact_paths[name]
            if isinstance(value, str):
                lines.append(f"- {name}: {value}")
    lines.extend(["", "## Warnings", ""])

    warnings = handoff.get("warnings")
    if isinstance(warnings, list) and warnings:
        for warning in warnings:
            if not isinstance(warning, dict):
                continue
            code = warning.get("code")
            message = warning.get("message")
            path = warning.get("path")
            if isinstance(code, str) and isinstance(message, str) and isinstance(path, str):
                lines.append(f"- {code} ({path}): {message}")
    else:
        lines.append("No warnings.")

    lines.extend(["", "## Missing Repo-Owned Gates", ""])

    missing_gates = handoff.get("missing_repo_owned_gates")
    if isinstance(missing_gates, list) and missing_gates:
        for gate in missing_gates:
            if not isinstance(gate, dict):
                continue
            gate_id = gate.get("id")
            severity = gate.get("severity")
            suggestion = gate.get("suggested_command")
            reason = gate.get("reason")
            if isinstance(gate_id, str) and isinstance(suggestion, str):
                lines.append(f"- {gate_id} ({severity}): add `{suggestion}`.")
                if isinstance(reason, str) and reason:
                    lines.append(f"  - Why: {reason}")
    else:
        lines.append("No missing repo-owned gates.")

    lines.extend(["", "## Runner-Provided Checks", ""])

    runner_checks = handoff.get("runner_provided_checks")
    if isinstance(runner_checks, list) and runner_checks:
        for check in runner_checks:
            if not isinstance(check, dict):
                continue
            check_id = check.get("id")
            finding_count = check.get("finding_count")
            description = check.get("description")
            if isinstance(check_id, str) and isinstance(finding_count, int):
                line = f"- {check_id}: {finding_count} finding"
                line += "" if finding_count == 1 else "s"
                if isinstance(description, str) and description:
                    line += f" ({description})"
                lines.append(line + ".")
    else:
        lines.append("No runner-provided structural checks produced findings.")

    lines.extend(["", "## Adoption Stage", ""])
    lines.extend(adoption_stage_markdown(handoff.get("adoption_stage")))

    lines.extend(["", "## Stopping Criteria", ""])
    lines.extend(_markdown_items(handoff.get("stopping_criteria")))

    lines.extend(["", "## Next Slice", ""])

    next_slice = handoff.get("next_slice")
    if isinstance(next_slice, dict):
        lines.extend(
            [
                f"- ID: {next_slice.get('id')}",
                f"- Title: {next_slice.get('title')}",
                f"- Priority: {next_slice.get('priority')}",
                "- Findings:",
                *_finding_markdown_items(next_slice.get("findings")),
                "- Actions:",
                *_markdown_items(next_slice.get("actions")),
            ]
        )
    else:
        lines.append("No remediation slice is queued.")

    lines.extend(["", "## Verification Gates", ""])
    lines.extend(_markdown_items(handoff.get("verification_gates")))

    lines.extend(["", "## Remediation Slices", ""])

    slice_ids = handoff.get("slice_ids")
    if isinstance(slice_ids, list) and slice_ids:
        lines.extend(_markdown_items(slice_ids))
    else:
        lines.append("No remediation slices are required.")

    return "\n".join(lines).rstrip() + "\n"


def _slice_for_finding(finding: dict[str, Any]) -> dict[str, Any]:
    finding_id = finding["id"]
    recommended_fix = finding["recommended_fix"]
    return {
        "id": f"remediate-{finding_id}",
        "title": f"Remediate {finding_id}",
        "priority": _priority_for_finding(finding),
        "findings": [
            {
                "id": finding_id,
                "severity": finding["severity"],
                "category": finding["category"],
                "summary": finding["summary"],
            }
        ],
        "actions": [
            f"Apply recommended fix: {recommended_fix}",
            f"Rerun quality-runner and confirm {finding_id} no longer appears.",
        ],
        "verification_gates": list(finding["verification"]),
    }


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


def _runner_provided_checks(audit_report: dict[str, Any]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for finding in _findings(audit_report):
        category = finding["category"]
        if not category.startswith("structural:"):
            continue
        check_id = category.removeprefix("structural:")
        counts[check_id] = counts.get(check_id, 0) + 1
    return [
        {
            "id": check_id,
            "finding_count": counts[check_id],
            "description": _runner_check_description(check_id),
        }
        for check_id in sorted(counts)
    ]


def _runner_check_description(check_id: str) -> str:
    descriptions = {
        "clarify": "readability and naming clarity heuristics",
        "deduplicate": "duplicate and near-duplicate detection",
        "harden": "API, error handling, and boundary hardening heuristics",
        "improve-tests": "test quality and coverage structure heuristics",
        "ponytail": "standard-library and native-platform replacement heuristics",
        "simplify": "complexity and nesting heuristics",
        "speed": "performance and unnecessary work heuristics",
        "ui_structural": "UI structure and frontend maintainability heuristics",
    }
    return descriptions.get(check_id, "Quality Runner structural heuristic")


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


def _next_slice(plan: dict[str, Any]) -> dict[str, Any] | None:
    slices = plan.get("slices")
    if not isinstance(slices, list) or not slices:
        return None
    first = slices[0]
    if not isinstance(first, dict):
        return None
    return {
        "id": first["id"],
        "title": first["title"],
        "priority": first["priority"],
        "findings": list(first["findings"]),
        "actions": list(first["actions"]),
        "verification_gates": list(first["verification_gates"]),
    }


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


def _markdown_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["- unavailable"]
    items = [item for item in value if isinstance(item, str) and item]
    if not items:
        return ["- unavailable"]
    return [f"- {item}" for item in items]


def _finding_markdown_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["- unavailable"]

    items: list[str] = []
    for finding in value:
        if not isinstance(finding, dict):
            continue
        finding_id = finding.get("id")
        summary = finding.get("summary")
        if isinstance(finding_id, str) and finding_id and isinstance(summary, str) and summary:
            items.append(f"- {finding_id}: {summary}")
    if not items:
        return ["- unavailable"]
    return items


def _finding_sort_key(finding: dict[str, Any]) -> tuple[int, int, str]:
    priority = _priority_for_finding(finding)
    score = finding.get("score")
    ranking_score = score if isinstance(score, int) else 0
    return PRIORITY_ORDER.get(priority, 99), -ranking_score, finding["id"]


def _priority_for_finding(finding: dict[str, Any]) -> str:
    severity = finding["severity"]
    if severity == "blocker":
        return "high"
    if severity == "warning":
        return "medium"
    return "low"


def _default_score(severity: str) -> int:
    return {"critical": 1000, "blocker": 900}.get(severity, 0)


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
