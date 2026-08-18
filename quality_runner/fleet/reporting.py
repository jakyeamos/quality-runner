from __future__ import annotations

from typing import Any


def summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# Quality Runner fleet environment-legibility audit `{summary['audit_id']}`",
        "",
        f"As of: `{summary['as_of']}`",
        "",
        f"Repositories: **{summary['repository_count']}**  ",
        f"Canonical coverage complete/incomplete: **{summary.get('audit_coverage_complete', 0)} / {summary.get('audit_coverage_incomplete', 0)}**  ",
        f"Mean applicable maturity: **{summary['mean_maturity']} / 4**  ",
        f"Dynamic selected/reused/passed: **{summary['dynamic_selected']} / {summary['dynamic_reused']} / {summary['dynamic_passed']}**",
        "",
        "## Dimension means",
        "",
        *(
            f"- {dimension}: {score if score is not None else 'N/A'} / 4"
            for dimension, score in summary["dimension_means"].items()
        ),
        "",
        "## Measurement gaps",
        "",
        *(f"- `{gap}`" for gap in summary["unresolved_measurement_gaps"][:40]),
        "",
        "Unknown, stale, and blocked evidence is excluded from green claims and remains visible in the private findings.",
        "",
    ]
    return "\n".join(lines)


def plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        f"# Environment-legibility remediation plan `{plan.get('plan_id')}`",
        "",
        f"Status: **{plan.get('status')}**  ",
        f"Confidence: **{plan.get('confidence')}**  ",
        f"{plan.get('observed_gap_summary')}",
        "",
    ]
    for priority in ("P0", "P1", "P2"):
        lines.extend([f"## {priority}", ""])
        tasks = plan.get("tasks", {}).get(priority, [])
        if not tasks:
            lines.append("- None")
        for task in tasks:
            lines.extend(
                [
                    f"- **{task.get('dimension')}**: {task.get('observed_gap')}",
                    f"  - Validate with: `{'; '.join(task.get('validation_commands', []))}`",
                    f"  - Acceptance: {'; '.join(task.get('acceptance_criteria', []))}",
                ]
            )
        lines.append("")
    lines.extend(
        [
            "## Local projection",
            "",
            "```markdown",
            str(plan.get("local_projection", {}).get("content", "")),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    return "\n".join(
        [
            "# Environment-legibility report",
            "",
            f"Audit: `{report.get('audit_id')}`",
            f"Mean maturity: **{summary.get('mean_maturity')} / 4**",
            f"Repositories: **{summary.get('repository_count')}**",
            "",
            "This is an aggregate, observational projection. Manual review is required before publication.",
            "",
        ]
    )
