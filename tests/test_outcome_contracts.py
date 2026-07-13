from __future__ import annotations

import json
from importlib import resources


def _outcome_schema() -> dict[str, object]:
    path = resources.files("quality_runner").joinpath("schemas/outcome.schema.json")
    return json.loads(path.read_text(encoding="utf-8"))


def test_outcome_schema_is_closed_and_versioned() -> None:
    schema = _outcome_schema()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema"] == {"const": "quality-runner-outcome-v0.2"}
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {
        "schema",
        "journey",
        "state",
        "assessment",
        "confidence",
        "writes",
        "safety",
        "next_action",
        "summary",
        "source",
    }
    assert "run_id" not in schema["required"]


def test_outcome_schema_preserves_the_journey_and_safety_vocabulary() -> None:
    schema = _outcome_schema()
    properties = schema["properties"]
    definitions = schema["$defs"]

    assert properties["journey"]["enum"] == ["audit", "review", "verify", "runs"]
    assert properties["state"]["enum"] == [
        "complete",
        "action-required",
        "awaiting-evidence",
        "blocked",
        "failed",
        "empty",
    ]
    assert definitions["confidence"]["additionalProperties"] is False
    assert definitions["writes"]["properties"]["source_worktree"] == {
        "enum": ["unchanged", "branch-switched"]
    }
    assert definitions["safety"]["properties"]["mode"] == {
        "enum": [
            "scan-only",
            "evidence-only",
            "disposable-execution",
            "read-only-history",
        ]
    }
    assert definitions["next_action"]["properties"]["kind"] == {
        "enum": [
            "read-handoff",
            "provide-review-output",
            "authorize-verification",
            "inspect-gate-failure",
            "inspect-run",
            "start-audit",
            "none",
        ]
    }
    assert definitions["history"]["required"] == [
        "runs",
        "truncated",
        "unavailable_run_ids",
    ]
