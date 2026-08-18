from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quality_runner.cli import build_parser
from quality_runner.fleet.audit import (
    fleet_audit_payload,
    fleet_replay_payload,
    fleet_report_payload,
)
from quality_runner.fleet.feed import fleet_feed_payload
from quality_runner.fleet.maturity_feed import MaturityFeedError
from quality_runner.fleet.summary import build_fleet_summary

AS_OF = "2026-08-13T17:00:00+00:00"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _matrix(*, status: str = "applicable") -> dict:
    surface = {
        "id": "matrix-maintenance",
        "scope": "local",
        "path": ".agents/change-surface-matrix.json",
        "owner": "repository-owner",
        "condition": "A material feature or functionality change is added or changed.",
        "operations": ["add", "change", "remove"],
        "validation": [
            "Update this matrix in the same change with affected surfaces and evidence.",
            "For a purely internal refactor, record a reviewed no-impact reason in the same change.",
        ],
        "status": status,
    }
    return {
        "schema_version": "change-surface-matrix/v1",
        "subject": {"kind": "repository", "id": "fixture"},
        "owner": "repository-owner",
        "last_reviewed": "2026-08-13",
        "surfaces": [surface],
        "unresolved_surfaces": [],
    }


def _init_repo(root: Path, matrix: dict | None = None) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "dev")
    _git(root, "config", "user.email", "qr-standard-tests@example.com")
    _git(root, "config", "user.name", "Quality Runner Standard Tests")
    (root / "README.md").write_text(
        "# Standard fixture\n\nRun the test command before completion.\n",
        encoding="utf-8",
    )
    if matrix is not None:
        path = root / ".agents/change-surface-matrix.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(matrix), encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")


def test_standard_fleet_audit_reports_every_repository_and_replays(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    _init_repo(projects / "current", _matrix())
    _init_repo(
        projects / "not-applicable",
        {
            **_matrix(),
            "surfaces": [
                {
                    "id": "matrix-maintenance",
                    "status": "not_applicable",
                    "reason": "Generated fixture has no feature lifecycle.",
                    "evidence": ["docs/generated-fixture-boundary.md"],
                }
            ],
        },
    )
    _init_repo(projects / "missing")

    audit = fleet_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit-output",
        standard="matrix-maintenance",
        as_of=AS_OF,
    )

    assert audit["standard"] == "matrix-maintenance"
    assert audit["repository_count"] == 3
    assert audit["summary"]["dimension_means"] == {"matrix_maintenance": 1.5}
    assert audit["summary"]["standard"] == "matrix-maintenance"
    assert audit["maturity_feed"]["status"] == "not_applicable"
    assert set(audit["standard_report"]["status_counts"]) == {
        "current",
        "missing",
        "not_applicable",
    }
    assert audit["standard_report"]["repository_count"] == 3
    assert all(
        isinstance(row["repository_path"], str) for row in audit["standard_report"]["repositories"]
    )

    artifact_root = Path(audit["artifact_root"])
    assert (artifact_root / "standard-report.json").is_file()
    findings = [
        json.loads(path.read_text()) for path in (artifact_root / "findings").glob("*.json")
    ]
    assert all(
        {finding["dimension"] for finding in item["findings"]} == {"matrix_maintenance"}
        for item in findings
    )
    assert all(item["behavior_assurance"] == {} for item in findings)

    replay = fleet_replay_payload(output_dir=artifact_root)
    assert replay["status"] == "passed"
    assert replay["deterministic"] is True

    report = fleet_report_payload(output_dir=artifact_root)
    assert report["standard"] == "matrix-maintenance"
    assert report["standard_report"]["repository_count"] == 3


def test_standard_fleet_audit_rejects_dynamic_and_canonical_feed_publication(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    _init_repo(projects / "fixture", _matrix())

    with pytest.raises(ValueError, match="static-only"):
        fleet_audit_payload(
            projects_root=projects,
            output_dir=tmp_path / "dynamic-output",
            standard="matrix-maintenance",
            dynamic=True,
        )

    audit = fleet_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit-output",
        standard="matrix-maintenance",
        as_of=AS_OF,
    )
    with pytest.raises(MaturityFeedError, match="standard-scoped"):
        fleet_feed_payload(output_dir=Path(audit["artifact_root"]))


def test_cli_exposes_one_standard_scope() -> None:
    args = build_parser().parse_args(
        ["fleet", "audit", "run", "--all", "--standard", "matrix-maintenance"]
    )

    assert args.standard == "matrix-maintenance"


def test_cli_exposes_developer_legibility_standard() -> None:
    args = build_parser().parse_args(
        ["fleet", "audit", "run", "--all", "--standard", "developer-legibility"]
    )

    assert args.standard == "developer-legibility"


def test_developer_legibility_summary_uses_its_maturity_scale() -> None:
    summary = build_fleet_summary(
        audit_id="audit-legibility",
        as_of=AS_OF,
        repositories=[],
        dynamic=False,
        changed_only=True,
        standard="developer-legibility",
    )

    assert summary["methodology"]["rubric"] == (
        "0 unknown, 1 ad hoc, 2 defined, 3 enforced, 4 newcomer verified"
    )


def test_long_running_task_standard_reports_two_dimensions(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repository = projects / "worker"
    _init_repo(repository)
    (repository / "worker.py").write_text(
        "# quality-runner: long-running-task id=reconcile\n"
        "def reconcile(items):\n"
        "    return [process(item) for item in items]\n",
        encoding="utf-8",
    )
    _git(repository, "add", "worker.py")
    _git(repository, "commit", "-m", "add worker")

    audit = fleet_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit-output",
        standard="long-running-tasks",
        as_of=AS_OF,
    )

    assert audit["standard_report"]["dimensions"] == [
        "long_running_task_observability",
        "long_running_task_optimization",
    ]
    assert "dimension" not in audit["standard_report"]
    assert set(audit["summary"]["dimension_means"]) == {
        "long_running_task_observability",
        "long_running_task_optimization",
    }
    row = audit["standard_report"]["repositories"][0]
    assert {assessment["dimension"] for assessment in row["assessments"]} == set(
        audit["standard_report"]["dimensions"]
    )
    persisted = [
        json.loads(path.read_text())
        for path in Path(audit["artifact_paths"]["findings_dir"]).glob("*.json")
    ][0]
    assert {finding["dimension"] for finding in persisted["findings"]} == {
        "long_running_task_observability",
        "long_running_task_optimization",
    }
