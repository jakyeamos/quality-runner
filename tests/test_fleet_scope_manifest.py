from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from quality_runner.fleet.scope_manifest import build_fleet_scope_manifest_from_pronto_status


def _repo(path: Path) -> None:
    path.mkdir(parents=True)
    (path / ".git").mkdir()


def test_scope_builder_writes_exact_sorted_pronto_population(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    alpha = projects / "alpha"
    beta = projects / "beta"
    _repo(alpha)
    _repo(beta)
    status = tmp_path / "pronto-status.json"
    status.write_text(
        json.dumps(
            {
                "generated_at": "2026-09-27T20:52:03Z",
                "repositories": [{"path": str(beta)}, {"path": str(alpha)}],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "fleet-scope.json"

    result = build_fleet_scope_manifest_from_pronto_status(
        status,
        projects_root=projects,
        output_path=output,
    )

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert result["repository_count"] == 2
    assert [item["path"] for item in manifest["repositories"]] == [str(alpha), str(beta)]
    assert {item["eligibility"] for item in manifest["repositories"]} == {"eligible"}


def test_scope_builder_fails_closed_for_unavailable_repository(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    projects.mkdir()
    status = tmp_path / "pronto-status.json"
    status.write_text(
        json.dumps(
            {
                "generated_at": "2026-09-27T20:52:03Z",
                "repositories": [{"path": str(projects / "missing")}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not an accessible Git checkout"):
        build_fleet_scope_manifest_from_pronto_status(
            status,
            projects_root=projects,
            output_path=tmp_path / "fleet-scope.json",
        )


def test_scope_builder_cli_is_machine_readable(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repository = projects / "alpha"
    _repo(repository)
    status = tmp_path / "pronto-status.json"
    status.write_text(
        json.dumps(
            {
                "generated_at": "2026-09-27T20:52:03Z",
                "repositories": [{"path": str(repository)}],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "fleet-scope.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "fleet",
            "scope",
            "build",
            "--pronto-status",
            str(status),
            "--projects-root",
            str(projects),
            "--output",
            str(output),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-fleet-scope-build/v1"
    assert payload["repository_count"] == 1
