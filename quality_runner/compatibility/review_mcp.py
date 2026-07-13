from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from quality_runner.application.journey_outcomes import review_journey_outcome
from quality_runner.cli_review import review_mcp_payload, review_mcp_tool
from quality_runner.core.outcome_contracts import JourneyOutcome


def review_mcp_journey_outcome(
    arguments: Mapping[str, object], *, repo_root: Path
) -> JourneyOutcome:
    return review_journey_outcome(
        review_mcp_payload(arguments, repo_root, include_extended_artifacts=True),
        repo_root=repo_root,
    )


def review_mcp_input_schema() -> dict[str, object]:
    input_schema = review_mcp_tool().get("inputSchema")
    if not isinstance(input_schema, dict):
        raise RuntimeError("review MCP tool is missing an input schema")
    return input_schema
