from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from quality_runner.application.review_v1_serializers import (
    review_manifest_from_v1,
    review_manifest_to_v1,
    review_packet_from_v1,
    review_packet_to_v1,
    review_report_from_v1,
    review_report_to_v1,
)
from quality_runner.mcp import call_tool

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "contracts" / "fresh-review" / "v1"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "name", ["task-context.json", "blind-context.json", "combined-context.json"]
)
def test_v1_review_packet_goldens_round_trip(name: str) -> None:
    payload = _fixture(name)

    assert review_packet_to_v1(review_packet_from_v1(payload)) == payload


@pytest.mark.parametrize(
    "name, optional_fields",
    [
        ("task-context.json", ["task", "repository_state", "changed_files"]),
        ("blind-context.json", ["repository_state", "changed_files"]),
        ("combined-context.json", ["packets"]),
    ],
)
def test_v1_review_packet_reader_preserves_schema_optional_fields(
    name: str, optional_fields: list[str]
) -> None:
    payload = _fixture(name)
    for field in optional_fields:
        payload.pop(field)

    assert review_packet_to_v1(review_packet_from_v1(payload)) == payload


def test_v1_review_packet_reader_preserves_schema_permitted_recursive_packets() -> None:
    payload = _fixture("blind-context.json")
    payload["packets"] = [_fixture("task-context.json")]

    assert review_packet_to_v1(review_packet_from_v1(payload)) == payload


def test_generated_v1_packets_match_m0_projection_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    import quality_runner.review_context as review_context
    from quality_runner.core.review_contracts import EvidenceReference
    from quality_runner.review_context import (
        build_review_context,
        build_review_packet,
        normalize_review_options,
    )

    root = Path("/quality-runner-v1-projection")
    evidence: list[EvidenceReference] = [
        {
            "path": "quality_runner/review_context.py",
            "kind": "file",
            "available": True,
            "note": "",
        }
    ]
    common_state = {"branch": "main", "clean": True}
    common_files = ["quality_runner/review_context.py", "tests/test_review_context.py"]
    common_omitted = ["browser access"]
    task_options = normalize_review_options(
        mode="task",
        scope="task",
        breadth="focused",
        task="Preserve the review projection",
        exclusions=["generated"],
        evidence=evidence,
        known_issues=["known-001"],
        include_known_issues=True,
        previous_summary="Prior implementation notes",
    )
    blind_options = normalize_review_options(
        mode="blind",
        scope="project",
        breadth="related",
        task=None,
        exclusions=["generated"],
        known_issues=["known-001"],
        include_known_issues=True,
    )
    combined_options = normalize_review_options(
        mode="combined",
        scope="project",
        breadth="related",
        task="Preserve the review projection",
        exclusions=["generated"],
        known_issues=["known-001"],
        include_known_issues=True,
        previous_summary="Prior implementation notes",
    )
    monkeypatch.setattr(review_context, "artifact_dir", lambda *_: root)

    actual = {
        "task": review_packet_to_v1(
            build_review_context(
                repo_root=root,
                run_id="baseline-task",
                options=task_options,
                repository_state=common_state,
                changed_files=common_files,
                omitted_evidence=common_omitted,
            )
        ),
        "blind": review_packet_to_v1(
            build_review_context(
                repo_root=root,
                run_id="baseline-blind",
                options=blind_options,
                repository_state=common_state,
                changed_files=common_files,
                omitted_evidence=common_omitted,
            )
        ),
        "combined": review_packet_to_v1(
            build_review_context(
                repo_root=root,
                run_id="baseline-combined",
                options=combined_options,
                repository_state=common_state,
                changed_files=common_files,
                omitted_evidence=common_omitted,
            )
        ),
        "direct_combined": review_packet_to_v1(
            build_review_packet(
                repo_root=root,
                run_id="baseline-direct-combined",
                options=combined_options,
                repository_state=common_state,
                changed_files=common_files,
                omitted_evidence=common_omitted,
            )
        ),
    }

    assert actual == _fixture("generated-packets.json")


def test_v1_review_packet_reader_rejects_schema_forbidden_object_fields() -> None:
    root = _fixture("blind-context.json")
    root["unexpected"] = True
    evidence = _fixture("task-context.json")
    evidence["evidence"][0]["unexpected"] = True
    freshness = _fixture("blind-context.json")
    freshness["freshness"]["unexpected"] = True

    for payload in (root, evidence, freshness):
        with pytest.raises(ValueError, match="unsupported fields"):
            review_packet_from_v1(payload)


def test_v1_review_manifest_golden_round_trips() -> None:
    payload = _fixture("task-manifest.json")

    assert review_manifest_to_v1(review_manifest_from_v1(payload)) == payload


def test_v1_review_manifest_reader_rejects_schema_forbidden_object_fields() -> None:
    root = _fixture("task-manifest.json")
    root["unexpected"] = True
    evidence = _fixture("task-manifest.json")
    evidence["evidence_references"][0]["unexpected"] = True
    freshness = _fixture("task-manifest.json")
    freshness["freshness"]["unexpected"] = True

    for payload in (root, evidence, freshness):
        with pytest.raises(ValueError, match="unsupported fields"):
            review_manifest_from_v1(payload)


@pytest.mark.parametrize("name", ["completed-report.json", "packet-ready-report.json"])
def test_v1_review_report_goldens_round_trip(name: str) -> None:
    payload = _fixture(name)

    assert review_report_to_v1(review_report_from_v1(payload)) == payload


def test_v1_review_report_reader_rejects_schema_forbidden_object_fields() -> None:
    root = _fixture("completed-report.json")
    root["unexpected"] = True
    published_extension = _fixture("completed-report.json")
    published_extension["next_action"] = "Use the v2 outcome for next-step guidance."
    counts = _fixture("completed-report.json")
    counts["severity_counts"]["unexpected"] = 0
    sections = _fixture("completed-report.json")
    sections["sections"]["unexpected"] = []
    finding = _fixture("completed-report.json")
    finding["findings"][0]["unexpected"] = True

    for payload in (root, published_extension, counts, sections, finding):
        with pytest.raises(ValueError, match="unsupported fields"):
            review_report_from_v1(payload)


def test_v1_review_report_reader_rejects_schema_invalid_counts_and_finding_strings() -> None:
    boolean_count = _fixture("completed-report.json")
    boolean_count["severity_counts"]["critical"] = True
    blank_location = copy.deepcopy(_fixture("completed-report.json"))
    blank_location["findings"][0]["location"] = [""]

    with pytest.raises(ValueError, match="severity counts"):
        review_report_from_v1(boolean_count)
    with pytest.raises(ValueError, match="location"):
        review_report_from_v1(blank_location)


def test_v1_readers_reject_invalid_freshness_and_task_provenance() -> None:
    invalid_freshness = _fixture("blind-context.json")
    invalid_freshness["freshness"]["new_invocation_required"] = False
    empty_provenance = _fixture("completed-report.json")
    empty_provenance["task_provenance"] = ""
    missing_provenance = _fixture("completed-report.json")
    missing_provenance.pop("task_provenance")

    with pytest.raises(ValueError, match="freshness"):
        review_packet_from_v1(invalid_freshness)
    assert review_report_to_v1(review_report_from_v1(empty_provenance)) == empty_provenance
    with pytest.raises(ValueError, match="task_provenance"):
        review_report_from_v1(missing_provenance)


def test_cli_and_mcp_packet_ready_projections_match_persisted_v1_artifacts(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "quality_runner",
        "review",
        str(tmp_path),
        "--mode",
        "blind",
        "--run-id",
        "cli-contract",
        "--legacy-output",
        "--json",
    ]
    cli = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    cli_payload = json.loads(cli.stdout)
    cli_report = json.loads(Path(cli_payload["artifact_paths"]["review_report_json"]).read_text())
    cli_context = json.loads(Path(cli_payload["artifact_paths"]["review_context_json"]).read_text())
    cli_manifest = json.loads(
        Path(cli_payload["artifact_paths"]["review_manifest_json"]).read_text()
    )

    assert cli_payload["report"] == cli_report
    assert review_packet_to_v1(review_packet_from_v1(cli_context)) == cli_context
    assert review_manifest_to_v1(review_manifest_from_v1(cli_manifest)) == cli_manifest
    assert review_report_to_v1(review_report_from_v1(cli_report)) == cli_report

    mcp = call_tool(
        "quality_runner_review",
        {"repo_root": str(tmp_path), "mode": "blind", "run_id": "mcp-contract"},
    )
    structured = mcp["structuredContent"]
    mcp_report = json.loads(Path(structured["artifact_paths"]["review_report_json"]).read_text())

    assert structured["report"] == mcp_report
    assert review_report_to_v1(review_report_from_v1(mcp_report)) == mcp_report


def test_legacy_review_projections_preserve_the_published_v1_shape(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "quality_runner",
        "review",
        str(tmp_path),
        "--mode",
        "blind",
        "--run-id",
        "published-v1-cli",
        "--legacy-output",
        "--json",
    ]
    cli = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    cli_payload = json.loads(cli.stdout)
    mcp = call_tool(
        "quality_runner_review",
        {"repo_root": str(tmp_path), "mode": "blind", "run_id": "published-v1-mcp"},
    )
    mcp_payload = mcp["structuredContent"]
    expected_result_keys = {
        "schema",
        "status",
        "run_id",
        "mode",
        "scope",
        "breadth",
        "adapter_status",
        "summary",
        "severity_counts",
        "evidence_unavailable",
        "artifact_paths",
        "saved_path",
        "report",
    }
    expected_report_keys = {
        "schema",
        "run_id",
        "mode",
        "scope",
        "breadth",
        "adapter_status",
        "task_provenance",
        "summary",
        "severity_counts",
        "evidence_used",
        "evidence_unavailable",
        "exclusions",
        "sections",
        "findings",
    }

    for payload in (cli_payload, mcp_payload):
        assert set(payload) == expected_result_keys
        assert set(payload["report"]) == expected_report_keys
        assert payload["summary"].startswith("Review packet ready:")
        persisted = json.loads(Path(payload["artifact_paths"]["review_report_json"]).read_text())
        assert payload["report"] == persisted


def test_default_cli_outcome_keeps_persisted_v1_review_artifacts_readable(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-m",
        "quality_runner",
        "review",
        str(tmp_path),
        "--mode",
        "blind",
        "--run-id",
        "outcome-artifact-contract",
        "--json",
    ]
    result = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    outcome = json.loads(result.stdout)
    paths = outcome["writes"]["artifact_paths"]
    context = json.loads(Path(paths["review_context_json"]).read_text())
    manifest = json.loads(Path(paths["review_manifest_json"]).read_text())
    report = json.loads(Path(paths["review_report_json"]).read_text())

    assert outcome["schema"] == "quality-runner-outcome-v0.2"
    assert review_packet_to_v1(review_packet_from_v1(context)) == context
    assert review_manifest_to_v1(review_manifest_from_v1(manifest)) == manifest
    assert review_report_to_v1(review_report_from_v1(report)) == report


@pytest.mark.parametrize("mode", ["task", "combined"])
def test_task_and_combined_cli_mcp_projections_preserve_v1_contracts(
    tmp_path: Path, mode: str
) -> None:
    task = "Preserve the public review projection"
    command = [
        sys.executable,
        "-m",
        "quality_runner",
        "review",
        str(tmp_path),
        "--mode",
        mode,
        "--scope",
        "project",
        "--task",
        task,
        "--known-issues",
        "known-001",
        "--run-id",
        f"cli-{mode}-contract",
        "--legacy-output",
        "--json",
    ]
    cli = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    cli_payload = json.loads(cli.stdout)
    cli_context, cli_report, cli_manifest = _persisted_review_payloads(cli_payload)

    _assert_public_review_projection(cli_payload, cli_context, cli_report, cli_manifest)
    expected_provenance = cli_context["input_hashes"]["task"] if mode == "task" else "None"
    assert cli_report["task_provenance"] == expected_provenance
    if mode == "combined":
        assert cli_context["packets"][1]["known_issues"] == ["known-001"]
    else:
        assert cli_context["known_issues"] == ["known-001"]

    mcp = call_tool(
        "quality_runner_review",
        {
            "repo_root": str(tmp_path),
            "mode": mode,
            "scope": "project",
            "task": task,
            "known_issues": ["known-001"],
            "run_id": f"mcp-{mode}-contract",
        },
    )
    structured = mcp["structuredContent"]
    mcp_context, mcp_report, mcp_manifest = _persisted_review_payloads(structured)

    _assert_public_review_projection(structured, mcp_context, mcp_report, mcp_manifest)
    assert mcp_report["task_provenance"] == (
        mcp_context["input_hashes"]["task"] if mode == "task" else "None"
    )


def _persisted_review_payloads(
    payload: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    paths = payload["artifact_paths"]
    return (
        json.loads(Path(paths["review_context_json"]).read_text()),
        json.loads(Path(paths["review_report_json"]).read_text()),
        json.loads(Path(paths["review_manifest_json"]).read_text()),
    )


def _assert_public_review_projection(
    payload: dict[str, object],
    context: dict[str, object],
    report: dict[str, object],
    manifest: dict[str, object],
) -> None:
    assert payload["report"] == report
    assert review_packet_to_v1(review_packet_from_v1(context)) == context
    assert review_manifest_to_v1(review_manifest_from_v1(manifest)) == manifest
    assert review_report_to_v1(review_report_from_v1(report)) == report


def test_contract_layers_preserve_inward_dependency_direction() -> None:
    forbidden_core_prefixes = (
        "quality_runner.application",
        "quality_runner.artifacts",
        "quality_runner.cli",
        "quality_runner.mcp",
        "quality_runner.review_",
    )
    core_imports = _imports(ROOT / "quality_runner" / "core" / "review_contracts.py")
    serializer_imports = _imports(
        ROOT / "quality_runner" / "application" / "review_v1_serializers.py"
    )
    report_serializer_imports = _imports(
        ROOT / "quality_runner" / "application" / "review_v1_reports.py"
    )
    serializer_quality_imports = {
        name for name in serializer_imports if name.startswith("quality_runner")
    }
    report_serializer_quality_imports = {
        name for name in report_serializer_imports if name.startswith("quality_runner")
    }

    assert not any(name.startswith(forbidden_core_prefixes) for name in core_imports)
    assert all(
        name.startswith(("quality_runner.core", "quality_runner.application.review_v1_reports"))
        for name in serializer_quality_imports
    )
    assert all(name.startswith("quality_runner.core") for name in report_serializer_quality_imports)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
