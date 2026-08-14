from __future__ import annotations

from typing import Any


def scan_projection(scan: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "schema",
        "package_manager",
        "languages",
        "ecosystems",
        "scripts",
        "quality_commands",
        "agent_instruction_files",
        "ci_files",
        "quality_contract",
        "warnings",
        "git_provenance",
    )
    return {key: scan[key] for key in keys if key in scan}


def plan_confidence(findings: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status")) for item in findings}
    if "blocked" in statuses:
        return "high"
    if "unknown" in statuses or "stale" in statuses:
        return "medium"
    return "medium"
