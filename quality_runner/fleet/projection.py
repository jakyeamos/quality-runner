from __future__ import annotations

from typing import Any

from quality_runner.fleet.contracts import DIMENSION_LABELS


def build_local_projection(
    repository: dict[str, Any],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    repo_id = str(repository["repo_id"])
    missing = [
        DIMENSION_LABELS[str(item["dimension"])]
        for item in findings
        if item.get("status") != "not_applicable" and _needs_remediation(item.get("score"))
    ]
    content = "\n".join(
        [
            "# Agent route",
            "",
            f"Repository identity: `{repo_id}` (Quality Runner fleet audit).",
            "",
            "Read this router first. Load deeper repository documentation only when the task matches its route.",
            "",
            "## Minimum route",
            "",
            "- Read the repository README and the relevant local context index before editing.",
            "- Use the discovered quality commands and preserve approval-gated paths.",
            "- Treat QR findings as evidence; missing or stale evidence is not a pass.",
            "- Record the target development branch and verify the source checkout before execution.",
            "",
            "## Current remediation focus",
            "",
            *(f"- {item}" for item in missing[:8]),
            "",
            "## Ownership",
            "",
            "- Quality Runner owns fleet evidence and remediation planning.",
            "- The repository owner approves local router changes and publishes documentation.",
            "",
        ]
    )
    return {
        "status": "review_required",
        "files": ["AGENTS.md", ".agents/context/README.md"],
        "content": content,
        "line_count": len(content.splitlines()),
        "source_edits": False,
    }


def _needs_remediation(score: object) -> bool:
    return not isinstance(score, (int, float)) or isinstance(score, bool) or score < 3
