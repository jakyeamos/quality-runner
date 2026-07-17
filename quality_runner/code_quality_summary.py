from __future__ import annotations

from typing import Any

from quality_runner.code_quality_similarity import NATIVE_SIMILARITY_ENGINE


def quality_summary_fields(
    *,
    backend: str,
    enabled: bool,
    disabled_groups: set[str],
    semantic_similarity_tools: dict[str, str],
    accountability: list[dict[str, Any]],
) -> dict[str, Any]:
    ui_file_count = _ui_file_count(accountability)
    return {
        "semantic_similarity_engine": (
            NATIVE_SIMILARITY_ENGINE if backend == "native" else "external-binary"
        ),
        "semantic_similarity_status": _similarity_module_status(
            semantic_similarity_tools,
            enabled=enabled,
            disabled="deduplicate" in disabled_groups,
        ),
        "ui_file_count": ui_file_count,
        "ui_quality_status": (
            "not_applicable"
            if ui_file_count == 0
            else "disabled"
            if "ui_structural" in disabled_groups
            else "enabled"
        ),
    }


def _similarity_module_status(
    tools: dict[str, str],
    *,
    enabled: bool,
    disabled: bool,
) -> str:
    if disabled or not enabled:
        return "disabled"
    statuses = set(tools.values())
    if "failed" in statuses or "missing" in statuses:
        return "unavailable"
    if "executed" in statuses or "enabled" in statuses:
        return "enabled"
    if "skipped" in statuses:
        return "disabled"
    if "not_applicable" in statuses:
        return "not_applicable"
    return "not_run"


def _ui_file_count(accountability: list[dict[str, Any]]) -> int:
    return sum(1 for item in accountability if "ui-structural" in item.get("check_coverage", []))
