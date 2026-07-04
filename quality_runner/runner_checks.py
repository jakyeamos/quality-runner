from __future__ import annotations

from typing import Any


def runner_provided_checks(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for finding in findings:
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
