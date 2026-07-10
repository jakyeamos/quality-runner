from __future__ import annotations

import json
from pathlib import Path

import pytest


def _schema(name: str) -> dict[str, object]:
    path = Path(__file__).parents[1] / "quality_runner" / "schemas" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_review_schemas_use_stable_schema_names_and_closed_top_level_objects() -> None:
    context = _schema("review-context.schema.json")
    manifest = _schema("review-manifest.schema.json")

    assert context["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert context["properties"]["schema"]["const"] == "quality-runner-review-context-v0.1"
    assert context["additionalProperties"] is False
    assert manifest["properties"]["schema"]["const"] == "quality-runner-review-manifest-v0.1"
    assert manifest["additionalProperties"] is False


def test_review_contracts_restrict_modes_scopes_and_breadths() -> None:
    from quality_runner.review_context import normalize_review_options

    assert normalize_review_options(mode="task", scope="task", breadth=None, task="Fix it")["mode"] == "task"
    assert normalize_review_options(mode="blind", scope="project", breadth=None, task=None)["breadth"] == "related"

    with pytest.raises(ValueError, match="mode"):
        normalize_review_options(mode="unknown", scope="task", breadth=None, task="Fix it")
    with pytest.raises(ValueError, match="scope"):
        normalize_review_options(mode="task", scope="unknown", breadth=None, task="Fix it")
    with pytest.raises(ValueError, match="breadth"):
        normalize_review_options(mode="blind", scope="project", breadth="wide", task=None)


def test_task_and_combined_modes_require_task_provenance() -> None:
    from quality_runner.review_context import normalize_review_options

    with pytest.raises(ValueError, match="task"):
        normalize_review_options(mode="task", scope="task", breadth=None, task=None)
    with pytest.raises(ValueError, match="task"):
        normalize_review_options(mode="combined", scope="project", breadth=None, task=" ")


def test_manifest_schema_requires_freshness_and_input_hashes() -> None:
    manifest = _schema("review-manifest.schema.json")
    required = set(manifest["required"])

    assert {"freshness", "input_hashes", "artifact_paths"}.issubset(required)
    assert "hidden_reasoning" not in manifest["properties"]
