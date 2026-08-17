from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quality_runner.fleet.audit import fleet_audit_payload
from quality_runner.fleet.certification import (
    CHECK_NAMES,
    CHECK_STATES,
    fleet_certification_payload,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "dev")
    _git(root, "config", "user.email", "qr-tests@example.com")
    _git(root, "config", "user.name", "Quality Runner Tests")
    (root / "README.md").write_text(
        """# Fixture

## Architecture
The repository has a small application boundary.

## Development
Run tests before completion. Last reviewed: 2026-07-26

## Security
Do not commit credentials.

## Definition of done
Acceptance criteria and quality gates pass.

## Deployment
Deployment uses a release rollback procedure.
""",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")


def _write_scope_manifest(path: Path, repository: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "quality-runner-fleet-scope/v1",
                "authority": "test fixture",
                "generated_at": "2026-08-17T00:00:00Z",
                "repositories": [
                    {
                        "path": str(repository),
                        "eligibility": "eligible",
                        "reason": "fixture repository",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_certification_projection_emits_numeric_counts_and_proof_states(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repository = projects / "fixture"
    _init_repo(repository)
    manifest = tmp_path / "scope.json"
    _write_scope_manifest(manifest, repository)
    output = tmp_path / "fleet-output"
    audit = fleet_audit_payload(
        projects_root=projects,
        output_dir=output,
        scope_manifest=manifest,
        as_of="2026-08-17T00:00:00+00:00",
    )

    result = fleet_certification_payload(
        projects_root=projects,
        scope_manifest=manifest,
        output_dir=output,
        audit_id=str(audit["audit_id"]),
        parallelism=2,
    )

    certification = result["certification"]
    assert result["schema"] == "quality-runner-fleet-certification-v0.1"
    assert certification["repository_count"] == 1
    assert certification["certified_count"] == 0
    assert certification["not_certified_count"] == 1
    assert result["status"] == "review_required"
    assert Path(result["artifact_paths"]["certification_json"]).is_file()
    assert Path(result["artifact_paths"]["certification_md"]).is_file()
    for name in CHECK_NAMES:
        assert set(certification["proof_check_counts"][name]) == set(CHECK_STATES)
        assert all(
            isinstance(value, int) for value in certification["proof_check_counts"][name].values()
        )


def test_certification_rejects_nonpositive_parallelism(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repository = projects / "fixture"
    _init_repo(repository)
    manifest = tmp_path / "scope.json"
    _write_scope_manifest(manifest, repository)

    try:
        fleet_certification_payload(
            projects_root=projects,
            scope_manifest=manifest,
            output_dir=tmp_path / "output",
            audit_id="missing",
            parallelism=0,
        )
    except ValueError as error:
        assert "parallelism" in str(error)
    else:
        raise AssertionError("nonpositive parallelism was accepted")
