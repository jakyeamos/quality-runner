from __future__ import annotations

from typing import Any

from quality_runner.adoption import adoption_stage_markdown
from quality_runner.handoff_gate_summary import action_group_markdown


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
        "## Domain Phase Candidates",
        "",
    ]

    phase_candidates = plan.get("phase_candidates")
    if isinstance(phase_candidates, list) and phase_candidates:
        for candidate in phase_candidates:
            if not isinstance(candidate, dict):
                continue
            lines.extend(
                [
                    f"### {candidate.get('id')}",
                    "",
                    f"- Domain: {candidate.get('domain')}",
                    f"- Title: {candidate.get('title')}",
                    f"- Priority: {candidate.get('priority')}",
                    f"- Status: {candidate.get('status')}",
                    f"- Leaf slices: {candidate.get('slice_count')}",
                    f"- Findings: {candidate.get('finding_count')}",
                    f"- Requires review: {str(candidate.get('requires_review')).lower()}",
                    "- Workstreams:",
                    *_markdown_items(candidate.get("workstreams")),
                    "- Representative leaf slices:",
                    *_markdown_items(candidate.get("representative_slice_ids")),
                    "- Representative paths:",
                    *_markdown_items(candidate.get("representative_paths")),
                    "- Actions:",
                    *_markdown_items(candidate.get("actions")),
                    "- Verification:",
                    *_markdown_items(candidate.get("verification_gates")),
                    "",
                ]
            )
    else:
        lines.extend(["No domain phase candidates are required.", ""])

    lines.extend(["## Slices (forensic detail)", ""])

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
                    f"- Verification mode: {slice_item.get('verification_mode', 'command')}",
                    "- Findings:",
                    *_finding_markdown_items(slice_item.get("findings")),
                    "- Actions:",
                    *_markdown_items(slice_item.get("actions")),
                    *action_group_markdown(slice_item.get("action_groups")),
                    "- Verification:",
                    *_markdown_items(slice_item.get("verification_gates")),
                    *_verification_requirements(slice_item),
                    "",
                ]
            )
    else:
        lines.extend(["No remediation slices are required.", ""])

    return "\n".join(lines).rstrip() + "\n"


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
            line = f"- {finding_id}: {summary}"
            actionability = finding.get("actionability")
            if isinstance(actionability, str) and actionability:
                line += f" [{actionability}]"
            items.append(line)
    if not items:
        return ["- unavailable"]
    return items


def _verification_requirements(slice_item: dict[str, Any]) -> list[str]:
    if slice_item.get("verification_mode") != "evidence":
        return []
    return [
        "- Evidence requirements:",
        *_markdown_items(slice_item.get("verification_requirements")),
    ]
