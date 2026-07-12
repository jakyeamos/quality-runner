from __future__ import annotations

import json
from pathlib import Path
from typing import get_type_hints

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

    assert (
        normalize_review_options(mode="task", scope="task", breadth=None, task="Fix it")["mode"]
        == "task"
    )
    assert (
        normalize_review_options(mode="blind", scope="project", breadth=None, task=None)["breadth"]
        == "related"
    )

    with pytest.raises(ValueError, match="mode"):
        normalize_review_options(mode="unknown", scope="task", breadth=None, task="Fix it")
    with pytest.raises(ValueError, match="scope"):
        normalize_review_options(mode="task", scope="unknown", breadth=None, task="Fix it")
    with pytest.raises(ValueError, match="breadth"):
        normalize_review_options(mode="blind", scope="project", breadth="wide", task=None)


def test_review_context_public_annotations_retain_v1_contracts() -> None:
    from quality_runner.review_context import (
        build_review_context,
        build_review_packet,
        normalize_review_options,
    )
    from quality_runner.review_types import ReviewOptions, ReviewPacket

    assert get_type_hints(normalize_review_options)["return"] is ReviewOptions
    assert get_type_hints(build_review_packet)["options"] is ReviewOptions
    assert get_type_hints(build_review_packet)["return"] is ReviewPacket
    assert get_type_hints(build_review_context)["options"] is ReviewOptions
    assert get_type_hints(build_review_context)["return"] is ReviewPacket


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


def test_task_packet_allowlist_includes_task_and_excludes_prior_review_documents(
    tmp_path: Path,
) -> None:
    from quality_runner.review_context import build_review_packet, normalize_review_options

    options = normalize_review_options(
        mode="task",
        scope="task",
        breadth="focused",
        task="Wire the settings route",
        exclusions=["styling"],
        previous_summary="Optional implementation summary",
        prior_review_documents=["review-001/review-report.md"],
        include_known_issues=True,
        known_issues=["known-001"],
    )
    packet = build_review_packet(
        repo_root=tmp_path,
        run_id="review-001",
        options=options,
        changed_files=["src/settings.py"],
        omitted_evidence=["browser access"],
    )

    assert packet["task"] == "Wire the settings route"
    assert packet["known_issues"] == ["known-001"]
    assert packet["previous_summary"] == "Optional implementation summary"
    assert "prior_review_documents" not in packet
    assert packet["freshness"]["prior_review_context_included"] is False
    assert packet["input_hashes"]["packet"]


def test_blind_packet_omits_task_summary_known_issues_and_prior_documents(tmp_path: Path) -> None:
    from quality_runner.review_context import build_review_packet, normalize_review_options

    options = normalize_review_options(
        mode="blind",
        scope="project",
        breadth="related",
        task="Do not expose this task",
        previous_summary="Do not expose this summary",
        prior_review_documents=["review-001/review-report.md"],
        include_known_issues=True,
        known_issues=["known-001"],
        active_cycle=True,
    )
    packet = build_review_packet(repo_root=tmp_path, run_id="review-002", options=options)

    assert packet["mode"] == "blind"
    assert "task" not in packet
    assert "previous_summary" not in packet
    assert "known_issues" not in packet
    assert packet["freshness"]["active_cycle"] is True
    assert packet["freshness"]["previous_agent_summary_included"] is False


def test_blind_and_combined_packets_preserve_known_issues_outside_active_cycles(
    tmp_path: Path,
) -> None:
    from quality_runner.review_context import build_review_context, normalize_review_options

    blind_options = normalize_review_options(
        mode="blind",
        scope="project",
        breadth="related",
        task=None,
        include_known_issues=True,
        known_issues=["known-001"],
    )
    blind = build_review_context(
        repo_root=tmp_path, run_id="review-blind-known", options=blind_options
    )
    combined_options = normalize_review_options(
        mode="combined",
        scope="project",
        breadth="related",
        task="Review the settings route",
        include_known_issues=True,
        known_issues=["known-001"],
        previous_summary="Prior implementation notes",
    )
    combined = build_review_context(
        repo_root=tmp_path, run_id="review-combined-known", options=combined_options
    )

    assert blind["known_issues"] == ["known-001"]
    assert combined["packets"][0]["known_issues"] == ["known-001"]
    assert combined["packets"][1]["known_issues"] == ["known-001"]
    assert "previous_summary" not in combined["packets"][1]


def test_direct_combined_packet_preserves_legacy_v1_projection(tmp_path: Path) -> None:
    from quality_runner.application.review_v1_serializers import (
        review_packet_from_v1,
        review_packet_to_v1,
    )
    from quality_runner.review_context import build_review_packet, normalize_review_options

    options = normalize_review_options(
        mode="combined",
        scope="project",
        breadth="related",
        task="Preserve direct combined packet callers",
        include_known_issues=True,
        known_issues=["known-001"],
        previous_summary="Prior implementation notes",
    )
    packet = build_review_packet(
        repo_root=tmp_path,
        run_id="direct-combined",
        options=options,
        repository_state={"branch": "main"},
        changed_files=["quality_runner/review_context.py"],
    )
    projection = review_packet_to_v1(packet)

    assert packet["mode"] == "combined"
    assert "packets" not in packet
    assert projection["task"] == "Preserve direct combined packet callers"
    assert projection["repository_state"] == {"branch": "main"}
    assert projection["changed_files"] == ["quality_runner/review_context.py"]
    assert projection["known_issues"] == ["known-001"]
    assert projection["previous_summary"] == "Prior implementation notes"
    assert review_packet_to_v1(review_packet_from_v1(projection)) == projection


def test_review_context_retains_legacy_defaults_for_partial_options(tmp_path: Path) -> None:
    from quality_runner.review_context import build_review_context
    from quality_runner.review_types import ReviewOptions, ReviewPacket

    packet = build_review_context(
        repo_root=tmp_path,
        run_id="legacy-options",
        options={"mode": "blind", "scope": "project", "breadth": "related"},
    )
    task = build_review_context(
        repo_root=tmp_path,
        run_id="legacy-task-options",
        options={
            "mode": "task",
            "scope": "task",
            "breadth": "focused",
            "task": "Preserve legacy defaults",
            "previous_summary": "",
        },
    )

    assert packet["exclusions"] == []
    assert packet["evidence"] == []
    assert packet["freshness"]["active_cycle"] is False
    assert "previous_summary" not in task
    assert ReviewOptions.__total__ is False
    assert ReviewPacket.__total__ is False
    assert ReviewOptions(mode="blind")["mode"] == "blind"
    assert ReviewPacket(mode="blind")["mode"] == "blind"


def test_combined_packet_contains_independent_task_and_blind_packets(tmp_path: Path) -> None:
    from quality_runner.review_context import build_review_context, normalize_review_options

    options = normalize_review_options(
        mode="combined",
        scope="project",
        breadth="related",
        task="Review the settings route",
    )
    packet = build_review_context(repo_root=tmp_path, run_id="review-003", options=options)
    child_packets = packet["packets"]

    assert [child["mode"] for child in child_packets] == ["task", "blind"]
    assert child_packets[0]["task"] == "Review the settings route"
    assert "task" not in child_packets[1]
    assert packet["input_hashes"]["task_packet"] != packet["input_hashes"]["blind_packet"]
    assert "findings" not in packet
