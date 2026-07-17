from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.skill_decomposition import write_skill_decomposition_artifacts

SECTION_TITLES = (
    ("missed_requirements", "Missed requirements"),
    ("confirmed_issues", "Confirmed issues"),
    ("suspected_issues", "Suspected issues"),
    ("not_enough_evidence", "Not enough evidence"),
    ("project_consistency_risks", "Project consistency risks"),
    ("regression_risks", "Regression risks"),
    ("known_accepted_issues", "Known accepted issues"),
    ("suggested_fixes", "Suggested fixes"),
    ("agent_handoff_prompts", "Agent handoff prompts"),
    ("remaining_uncertainty", "Remaining uncertainty"),
)


def persist_review_artifacts(
    *,
    repo_root: Path,
    run_id: str,
    manifest: Mapping[str, object],
    context: Mapping[str, object],
    report: Mapping[str, object],
    save: bool = True,
    decomposition_report: Mapping[str, object] | None = None,
) -> dict[str, str]:
    if not save:
        return {}
    run_dir = prepare_artifact_dir(repo_root, run_id)
    paths = {
        "review_manifest_json": run_dir / "review-manifest.json",
        "review_context_json": run_dir / "review-context.json",
        "review_report_json": run_dir / "review-report.json",
        "review_report_md": run_dir / "review-report.md",
        "review_agent_packet_md": run_dir / "review-agent-packet.md",
        "review_fix_prompts_md": run_dir / "review-fix-prompts.md",
    }
    write_json(paths["review_manifest_json"], dict(manifest))
    write_json(paths["review_context_json"], dict(context))
    write_json(paths["review_report_json"], dict(report))
    write_text(paths["review_report_md"], render_review_markdown(report))
    write_text(paths["review_agent_packet_md"], render_agent_packet(context))
    write_text(paths["review_fix_prompts_md"], render_fix_prompts(report))
    result = {name: str(path) for name, path in paths.items()}
    if decomposition_report is not None:
        result.update(
            write_skill_decomposition_artifacts(
                run_dir=run_dir,
                report=decomposition_report,
            )
        )
    return result


def render_review_markdown(report: Mapping[str, object]) -> str:
    lines = [
        "# Fresh Review Report",
        "",
        f"- Run: `{report.get('run_id', 'unknown')}`",
        f"- Mode: `{report.get('mode', 'unknown')}`",
        f"- Scope: `{report.get('scope', 'unknown')}`",
        f"- Breadth: `{report.get('breadth', 'unknown')}`",
        f"- Adapter status: `{report.get('adapter_status', 'unknown')}`",
        "",
        f"## Summary\n\n{report.get('summary', 'Review status unavailable.')}",
        "",
    ]
    lines.extend(_metadata_section("Evidence used", report.get("evidence_used")))
    lines.extend(_metadata_section("Evidence unavailable", report.get("evidence_unavailable")))
    lines.extend(_metadata_section("Exclusions", report.get("exclusions")))
    next_action = report.get("next_action")
    if isinstance(next_action, str) and next_action:
        lines.extend(["## Next action", "", next_action, ""])
    sections = report.get("sections")
    sections_map = sections if isinstance(sections, Mapping) else {}
    for key, title in SECTION_TITLES:
        lines.extend([f"## {title}", ""])
        lines.extend(_section_items(sections_map.get(key)))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_agent_packet(context: Mapping[str, object]) -> str:
    return "\n".join(
        [
            "# Fresh Review Agent Packet",
            "",
            "Use only the context below. This packet is a new review invocation.",
            "Do not infer or request prior implementation-agent reasoning.",
            "",
            "```json",
            json.dumps(dict(context), indent=2, sort_keys=True),
            "```",
            "",
        ]
    )


def render_combined_agent_packet_guide() -> str:
    """Keep the coordinator artifact free of task content for blind-review isolation."""
    return "\n".join(
        [
            "# Fresh Review Combined Packet Guide",
            "",
            "Run two separately scoped reviews before grouping findings locally.",
            "",
            "- Give `review-agent-packet-task.md` only to the task-aware reviewer.",
            "- Give `review-agent-packet-blind.md` only to the blind reviewer.",
            "- Return both bound entries in `review-adapter-response.template.json`.",
            "",
        ]
    )


def render_fix_prompts(
    report: Mapping[str, object], *, selected_findings: Sequence[Mapping[str, object]] | None = None
) -> str:
    lines = [
        "# Fresh Review Fix Prompts",
        "",
        "These prompts are for a separate fixing agent. Quality Runner does not edit source files.",
        "Investigate each finding, stay within the declared scope, obtain approval before edits, and verify the result.",
        "",
    ]
    findings: object = (
        selected_findings if selected_findings is not None else report.get("findings")
    )
    if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)) or not findings:
        if report.get("adapter_status") != "review-complete":
            lines.append("No fixing prompts were generated because a review did not complete.")
            next_action = report.get("next_action")
            if isinstance(next_action, str) and next_action:
                lines.append(next_action)
            return "\n".join(lines).rstrip() + "\n"
        if selected_findings is not None:
            lines.append(
                "No fixing prompts were generated; select findings before handing work to a fixer."
            )
        else:
            lines.append("No finding-specific prompts were generated.")
        return "\n".join(lines).rstrip() + "\n"
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        finding_id = finding.get("id", "unknown")
        prompt = finding.get("agent_prompt", "Investigate this finding and report what you find.")
        location = finding.get("location", [])
        lines.extend(
            [
                f"## {finding_id}",
                "",
                f"- Severity: `{finding.get('severity', 'unknown')}`",
                f"- Confidence: `{finding.get('confidence', 'unknown')}`",
                f"- Inspect: {', '.join(_strings(location)) or 'location not provided'}",
                "",
                str(prompt),
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _metadata_section(title: str, value: object) -> list[str]:
    return [f"## {title}", "", *_section_items(value), ""]


def _section_items(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not value:
        return ["- None"]
    lines: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            finding_id = item.get("id", "finding")
            summary = item.get("summary", item.get("recommended_fix", item.get("agent_prompt", "")))
            lines.append(f"- **{finding_id}**: {summary}")
        else:
            lines.append(f"- {item}")
    return lines


def _strings(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, str)]
