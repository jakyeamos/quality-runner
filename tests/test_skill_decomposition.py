from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "decomposition"


def _fixture_units(path: Path) -> tuple[str, list[Mapping[str, object]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    fixture_id = payload.get("fixture_id")
    evidence = payload.get("evidence")
    assert isinstance(fixture_id, str)
    assert isinstance(evidence, list)
    return fixture_id, [cast(Mapping[str, object], item) for item in evidence]


def _ledger_fixture_report(run_id: str) -> dict[str, object]:
    fixture_ids: list[str] = []
    units: list[Mapping[str, object]] = []
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        fixture_id, fixture_units = _fixture_units(path)
        fixture_ids.append(fixture_id)
        units.extend(fixture_units)

    from quality_runner.skill_decomposition import build_skill_decomposition_report

    return build_skill_decomposition_report(
        run_id=run_id,
        units=units,
        fixture_ids=fixture_ids,
    )


def test_ledger_fixtures_build_report_only_contract() -> None:
    from quality_runner.schema_constants import SKILL_DECOMPOSITION_SCHEMA
    from quality_runner.skill_decomposition import validate_skill_decomposition_report

    report = _ledger_fixture_report("decomposition-fixtures")
    validation = validate_skill_decomposition_report(report)
    summary = cast(dict[str, int], report["summary"])
    units = cast(list[Mapping[str, object]], report["units"])

    assert validation["passed"] is True
    assert report["schema"] == SKILL_DECOMPOSITION_SCHEMA
    assert report["status"] == "report-only"
    assert report["implementation_allowed"] is False
    assert len(units) == 12
    assert summary["source_units"] == 12
    assert summary["mapped_units"] == 8
    assert summary["context_only_units"] == 4
    assert summary["loss_units"] == 4
    assert summary["evidence_preserved_units"] == 12
    assert summary["evidence_not_preserved_units"] == 0

    required_fields = {
        "source",
        "revision",
        "path",
        "locator",
        "knowledge_role",
        "enforceability",
        "normalization_status",
        "evidence_preserved",
        "mapping_status",
        "loss_reason",
    }
    assert all(required_fields <= set(unit) for unit in units)
    assert {str(unit["source"]): str(unit["revision"]) for unit in units} == {
        "kepano/obsidian-skills": "a1dc48e68138490d522c04cbf5822214c6eb1202",
        "kepano/defuddle": "6c39f0959a2f566469a93a190b50e4b34bcf52c4",
        "kepano/clipper-templates": "b8c7df190d6daada5d07a95b072853e64f020cb3",
    }


def test_sidecar_persistence_is_report_only_and_does_not_promote_corpus(
    tmp_path: Path,
) -> None:
    from quality_runner.skill_decomposition import persist_skill_decomposition_artifacts

    report = _ledger_fixture_report("decomposition-persist")
    paths = persist_skill_decomposition_artifacts(
        repo_root=tmp_path,
        run_id="decomposition-persist",
        report=report,
    )
    run_dir = tmp_path / ".quality-runner" / "runs" / "decomposition-persist"

    assert set(paths) == {"skill_decomposition_json", "skill_decomposition_md"}
    persisted = json.loads((run_dir / "skill-decomposition.json").read_text(encoding="utf-8"))
    assert persisted == report
    markdown = (run_dir / "skill-decomposition.md").read_text(encoding="utf-8")
    assert "Implementation allowed: `false`" in markdown
    assert "product-identity-gap" in markdown
    assert not (tmp_path / ".quality-runner" / "skills").exists()
    assert not (tmp_path / ".quality-runner.toml").exists()


def test_sidecar_dry_run_writes_nothing(tmp_path: Path) -> None:
    from quality_runner.skill_decomposition import persist_skill_decomposition_artifacts

    paths = persist_skill_decomposition_artifacts(
        repo_root=tmp_path,
        run_id="decomposition-dry-run",
        report=_ledger_fixture_report("decomposition-dry-run"),
        save=False,
    )

    assert paths == {}
    assert not (tmp_path / ".quality-runner").exists()


def test_optional_review_artifact_path_writes_only_sidecar(tmp_path: Path) -> None:
    from quality_runner.review_artifacts import persist_review_artifacts

    report = _ledger_fixture_report("decomposition-workflow")
    paths = persist_review_artifacts(
        repo_root=tmp_path,
        run_id="decomposition-workflow",
        manifest={},
        context={},
        report={},
        decomposition_report=report,
    )

    assert set(paths) == {
        "review_manifest_json",
        "review_context_json",
        "review_report_json",
        "review_report_md",
        "review_agent_packet_md",
        "review_fix_prompts_md",
        "skill_decomposition_json",
        "skill_decomposition_md",
    }
    assert Path(paths["skill_decomposition_json"]).exists()
    assert not (tmp_path / ".quality-runner" / "skills").exists()
    assert not (tmp_path / ".quality-runner.toml").exists()


def test_decomposition_rejects_loss_without_reason() -> None:
    from quality_runner.skill_decomposition import build_skill_decomposition_report

    with pytest.raises(ValueError, match="loss_reason is required"):
        build_skill_decomposition_report(
            run_id="invalid-decomposition",
            units=[
                {
                    "id": "missing-loss-reason",
                    "source": "example/source",
                    "revision": "revision",
                    "path": "source.md",
                    "locator": "L1",
                    "knowledge_role": "workflow",
                    "enforceability": "context_only",
                    "normalization_status": "not_applicable",
                    "evidence": "Evidence remains bounded.",
                    "evidence_preserved": True,
                    "mapping_status": "context_only",
                    "mapping_target": None,
                    "loss_reason": None,
                }
            ],
        )
