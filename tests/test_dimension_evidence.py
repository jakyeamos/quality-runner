from __future__ import annotations

import json
from pathlib import Path

import pytest

from quality_runner.fleet.dimension_evidence import (
    EVIDENCE_DIMENSIONS,
    assess_dimension_evidence,
    load_dimension_evidence,
)
from quality_runner.fleet.legibility import audit_repository


def _write_contract(
    root: Path,
    *,
    dimensions: dict[str, object],
    last_reviewed: str = "2026-08-01",
) -> None:
    (root / ".agents").mkdir(parents=True, exist_ok=True)
    (root / ".agents/environment-legibility.json").write_text(
        json.dumps(
            {
                "schema_version": "quality-runner-environment-legibility/v1",
                "owner": "repository-owner",
                "last_reviewed": last_reviewed,
                "dimensions": dimensions,
            }
        ),
        encoding="utf-8",
    )


def _dimension_entry(*, automated: bool) -> dict[str, object]:
    entry: dict[str, object] = {
        "evidence": ["docs/architecture.md"],
        "validation": [
            {
                "path": "tests/test_architecture.py",
                "contains": ["test_architecture_boundary"],
            }
        ],
    }
    if automated:
        entry["automation"] = [
            {
                "path": ".github/workflows/ci.yml",
                "contains": ["pytest tests/test_architecture.py"],
            }
        ]
    return entry


def _write_evidence_surfaces(root: Path) -> None:
    (root / "docs").mkdir(parents=True)
    (root / "docs/architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests/test_architecture.py").write_text(
        "def test_architecture_boundary() -> None:\n    assert True\n",
        encoding="utf-8",
    )
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/ci.yml").write_text(
        "jobs:\n  architecture:\n    run: pytest tests/test_architecture.py\n",
        encoding="utf-8",
    )


def test_current_validated_contract_scores_three_without_automation(tmp_path: Path) -> None:
    _write_evidence_surfaces(tmp_path)
    _write_contract(
        tmp_path,
        dimensions={"architecture_boundaries": _dimension_entry(automated=False)},
    )

    contract = load_dimension_evidence(tmp_path, "2026-08-01T12:00:00+00:00")
    result = assess_dimension_evidence(tmp_path, contract, "architecture_boundaries")

    assert result is not None
    assert result["score"] == 3
    assert result["status"] == "validated"


def test_current_automated_contract_scores_four(tmp_path: Path) -> None:
    _write_evidence_surfaces(tmp_path)
    _write_contract(
        tmp_path,
        dimensions={"architecture_boundaries": _dimension_entry(automated=True)},
    )

    contract = load_dimension_evidence(tmp_path, "2026-08-01T12:00:00+00:00")
    result = assess_dimension_evidence(tmp_path, contract, "architecture_boundaries")

    assert result is not None
    assert result["score"] == 4
    assert result["status"] == "maintained"


@pytest.mark.parametrize("dimension", sorted(EVIDENCE_DIMENSIONS))
def test_all_previously_capped_dimensions_have_a_four_point_route(
    tmp_path: Path,
    dimension: str,
) -> None:
    _write_evidence_surfaces(tmp_path)
    _write_contract(tmp_path, dimensions={dimension: _dimension_entry(automated=True)})

    contract = load_dimension_evidence(tmp_path, "2026-08-01T12:00:00+00:00")
    result = assess_dimension_evidence(tmp_path, contract, dimension)

    assert result is not None
    assert result["score"] == 4


def test_stale_contract_is_capped_at_two(tmp_path: Path) -> None:
    _write_evidence_surfaces(tmp_path)
    _write_contract(
        tmp_path,
        dimensions={"architecture_boundaries": _dimension_entry(automated=True)},
        last_reviewed="2025-01-01",
    )

    contract = load_dimension_evidence(tmp_path, "2026-08-01T12:00:00+00:00")
    result = assess_dimension_evidence(tmp_path, contract, "architecture_boundaries")

    assert result is not None
    assert result["score"] == 2
    assert result["status"] == "stale"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "schema_version": "quality-runner-environment-legibility/v1",
            "owner": "",
            "last_reviewed": "2026-08-01",
            "dimensions": {},
        },
        {
            "schema_version": "quality-runner-environment-legibility/v1",
            "owner": "repository-owner",
            "last_reviewed": "not-a-date",
            "dimensions": {},
        },
        {
            "schema_version": "quality-runner-environment-legibility/v1",
            "owner": "repository-owner",
            "last_reviewed": "2026-08-01",
            "dimensions": [],
        },
    ],
)
def test_invalid_contract_roots_fail_closed(tmp_path: Path, payload: object) -> None:
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents/environment-legibility.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    contract = load_dimension_evidence(tmp_path, "2026-08-01T12:00:00+00:00")
    result = assess_dimension_evidence(tmp_path, contract, "architecture_boundaries")

    assert contract["status"] == "invalid"
    assert result is not None
    assert result["score"] == 2
    assert result["status"] == "unknown"


def test_malformed_json_fails_closed(tmp_path: Path) -> None:
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents/environment-legibility.json").write_text("{", encoding="utf-8")

    contract = load_dimension_evidence(tmp_path, "2026-08-01T12:00:00+00:00")

    assert contract["status"] == "invalid"


def test_unsafe_or_unmatched_assertions_fail_closed(tmp_path: Path) -> None:
    _write_evidence_surfaces(tmp_path)
    entry = _dimension_entry(automated=True)
    entry["evidence"] = ["../outside.md"]
    entry["automation"] = [{"path": ".github/workflows/ci.yml", "contains": ["missing-command"]}]
    _write_contract(tmp_path, dimensions={"architecture_boundaries": entry})

    contract = load_dimension_evidence(tmp_path, "2026-08-01T12:00:00+00:00")
    result = assess_dimension_evidence(tmp_path, contract, "architecture_boundaries")

    assert result is not None
    assert result["score"] == 2
    assert result["status"] == "unknown"
    assert "incomplete" in result["message"].lower()


def test_repository_audit_uses_structured_evidence_without_promoting_prose(
    tmp_path: Path,
) -> None:
    _write_evidence_surfaces(tmp_path)
    repository = {"repo_id": "repo-fixture", "primary_path": str(tmp_path)}

    prose_only = audit_repository(
        repository=repository,
        as_of="2026-08-01T12:00:00+00:00",
        run_id="prose-only",
    )
    prose_findings = {item["dimension"]: item for item in prose_only["findings"]}
    assert prose_findings["architecture_boundaries"]["score"] == 2

    _write_contract(
        tmp_path,
        dimensions={"architecture_boundaries": _dimension_entry(automated=True)},
    )
    evidenced = audit_repository(
        repository=repository,
        as_of="2026-08-01T12:00:00+00:00",
        run_id="structured-evidence",
    )
    evidenced_findings = {item["dimension"]: item for item in evidenced["findings"]}
    assert evidenced_findings["architecture_boundaries"]["score"] == 4
    assert evidenced_findings["architecture_boundaries"]["status"] == "maintained"
