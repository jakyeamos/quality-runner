from __future__ import annotations

from typing import Any

from quality_runner.adoption import adoption_stage_markdown
from quality_runner.handoff_gate_summary import action_group_markdown, gate_verification_markdown
from quality_runner.intent import intent_markdown_lines
from quality_runner.security.handoff import security_review_markdown


def render_handoff_markdown(handoff: dict[str, Any]) -> str:
    lines = [
        "# Quality Runner Agent Handoff",
        "",
        f"- Schema: {handoff.get('schema')}",
        f"- Status: {handoff.get('status')}",
        f"- Implementation allowed: {str(handoff.get('implementation_allowed')).lower()}",
        "",
    ]
    lifecycle_status = handoff.get("lifecycle_status")
    if isinstance(lifecycle_status, str) and lifecycle_status:
        lines.extend([f"- Lifecycle status: {lifecycle_status}", ""])

    lines.extend(intent_markdown_lines(handoff.get("intent")))
    lines.extend(
        [
            *(gate_verification_markdown(handoff.get("gate_verification"))),
            "",
            "## Artifacts",
            "",
        ]
    )

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

    security_lines = security_review_markdown(handoff.get("security_review"))
    if security_lines:
        lines.extend(security_lines)

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
                *action_group_markdown(next_slice.get("action_groups")),
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
