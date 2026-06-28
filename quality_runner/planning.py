from __future__ import annotations

from typing import Any

from quality_runner.findings import AGENT_HANDOFF_SCHEMA, REMEDIATION_PLAN_SCHEMA

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def build_remediation_plan(
    *,
    audit_report: dict[str, Any],
    capability_map: dict[str, Any],
) -> dict[str, Any]:
    findings = sorted(_findings(audit_report), key=_finding_sort_key)
    slices = [_slice_for_finding(finding) for finding in findings]

    return {
        "schema": REMEDIATION_PLAN_SCHEMA,
        "run_id": _string_or_none(audit_report.get("run_id")),
        "profile": _string_or_none(audit_report.get("profile")),
        "implementation_allowed": False,
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
) -> dict[str, Any]:
    status = "clean" if not _slices(remediation_plan) else "planned"
    next_slice = _next_slice(remediation_plan)
    return {
        "schema": AGENT_HANDOFF_SCHEMA,
        "run_id": _string_or_none(audit_report.get("run_id")),
        "status": status,
        "implementation_allowed": False,
        "artifact_paths": artifact_paths,
        "warnings": _warnings(remediation_plan),
        "finding_ids": [finding["id"] for finding in _findings(audit_report)],
        "slice_ids": [slice_item["id"] for slice_item in _slices(remediation_plan)],
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


def _finding_sort_key(finding: dict[str, Any]) -> tuple[int, str]:
    priority = _priority_for_finding(finding)
    return PRIORITY_ORDER.get(priority, 99), finding["id"]


def _priority_for_finding(finding: dict[str, Any]) -> str:
    severity = finding["severity"]
    if severity == "blocker":
        return "high"
    if severity == "warning":
        return "medium"
    return "low"


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None
