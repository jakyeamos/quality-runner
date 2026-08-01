from __future__ import annotations

from typing import Any, cast

from quality_runner.adoption import adoption_stage_markdown
from quality_runner.handoff_gate_summary import action_group_markdown, gate_verification_markdown
from quality_runner.intent import intent_markdown_lines
from quality_runner.intent_docs import intent_docs_markdown_lines
from quality_runner.security.handoff import security_review_markdown
from quality_runner.workflow_skills import skill_review_markdown


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
    lines.extend(intent_docs_markdown_lines(handoff.get("intent_docs")))
    lines.extend(skill_review_markdown(handoff.get("skill_review")))
    lines.extend(
        [
            *(gate_verification_markdown(handoff.get("gate_verification"))),
            "",
            "## Artifacts",
            "",
        ]
    )

    artifact_paths = handoff.get("artifact_paths")
    artifact_paths_map = _dict(artifact_paths)
    if artifact_paths_map is not None:
        for name in sorted(artifact_paths_map):
            value = artifact_paths_map[name]
            if isinstance(value, str):
                lines.append(f"- {name}: {value}")
    lines.extend(["", "## Warnings", ""])

    warnings = handoff.get("warnings")
    if isinstance(warnings, list) and warnings:
        for warning in _dict_list(cast(object, warnings)):
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
        for gate in _dict_list(cast(object, missing_gates)):
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
        for check in _dict_list(cast(object, runner_checks)):
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

    lines.extend(["", "## Domain Phase Candidates", ""])
    phase_candidates = handoff.get("phase_candidates")
    if isinstance(phase_candidates, list) and phase_candidates:
        for candidate in _dict_list(cast(object, phase_candidates)):
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
        lines.append("No domain phase candidates are required.")

    lines.extend(["", "## Next Slice", ""])

    next_slice = handoff.get("next_slice")
    next_slice_map = _dict(next_slice)
    if next_slice_map is not None:
        lines.extend(
            [
                f"- ID: {next_slice_map.get('id')}",
                f"- Title: {next_slice_map.get('title')}",
                f"- Priority: {next_slice_map.get('priority')}",
                f"- Verification mode: {next_slice_map.get('verification_mode', 'command')}",
                "- Findings:",
                *_finding_markdown_items(next_slice_map.get("findings")),
                "- Actions:",
                *_markdown_items(next_slice_map.get("actions")),
                *action_group_markdown(next_slice_map.get("action_groups")),
                *_verification_requirements(next_slice_map),
            ]
        )
    else:
        lines.append("No remediation slice is queued.")

    lines.extend(["", "## Verification Gates", ""])
    lines.extend(_markdown_items(handoff.get("verification_gates")))

    lines.extend(["", "## Remediation Slices", ""])

    slice_ids = handoff.get("slice_ids")
    if isinstance(slice_ids, list) and slice_ids:
        lines.extend(_markdown_items(cast(object, slice_ids)))
    else:
        lines.append("No remediation slices are required.")

    return "\n".join(lines).rstrip() + "\n"


def _markdown_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["- unavailable"]
    items = [item for item in cast(list[Any], value) if isinstance(item, str) and item]
    if not items:
        return ["- unavailable"]
    return [f"- {item}" for item in items]


def _finding_markdown_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return ["- unavailable"]

    items: list[str] = []
    for finding in _dict_list(cast(object, value)):
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
        "- Verification requirements:",
        *_markdown_items(slice_item.get("verification_requirements")),
    ]


def _dict(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for raw_item in cast(list[Any], value) if (item := _dict(raw_item)) is not None]
