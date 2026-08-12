from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quality_runner.ci_gate_audit import CI_GATE_AUDIT_SCHEMA, audit_ci_gate_candidates
from quality_runner.cli import main
from quality_runner.fleet.audit import fleet_audit_payload, fleet_replay_payload
from quality_runner.fleet.maturity_feed import build_maturity_feed


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _migration_repo(root: Path) -> str:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "dev")
    _git(root, "config", "user.email", "ci-gate-audit@example.com")
    _git(root, "config", "user.name", "CI Gate Audit")
    _write(root / "migrations/001_add_state.sql", "alter table jobs add column state text;\n")
    _write(root / "src/database.py", "DATABASE_URL = 'sqlite:///app.db'\n")
    _write(
        root / "README.md",
        "# Service\n\nProduction deploys preserve rollback compatibility during migrations.\n",
    )
    _write(
        root / ".github/workflows/migrations.yml",
        "name: Migration safety\non: pull_request\njobs:\n  migration-compatibility:\n    runs-on: ubuntu-latest\n",
    )
    _write(
        root / "tests/test_migration_rollback.py",
        "def test_rejects_incompatible_rollback():\n    assert 'rollback' != 'invalid migration'\n",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    return _git(root, "rev-parse", "HEAD")


def test_semantic_audit_requires_independent_repository_signals(tmp_path: Path) -> None:
    repo = tmp_path / "service"
    head = _migration_repo(repo)
    report = audit_ci_gate_candidates(
        repo, generated_at="2026-08-11T23:30:00+00:00", branch="dev", head_sha=head
    )

    migration = next(
        candidate
        for candidate in report["candidates"]
        if candidate["id"] == "custom:migration_compatibility"
    )
    assert report["schema"] == CI_GATE_AUDIT_SCHEMA
    assert report["repository"] == {"name": "service", "branch": "dev", "head_sha": head}
    assert report["policy"]["authority"] == "recommendation_only"
    assert report["policy"]["implementation_allowed"] is False
    assert migration["confidence"] == "high"
    assert migration["existing_check"]["status"] == "related_context_found"
    assert migration["negative_controls"] == [
        {
            "path": "tests/test_migration_rollback.py",
            "reason": "test or fixture covers migration",
        }
    ]
    assert migration["admission"]["state"] == "implementation_detected"
    assert any(
        "Repository-owned policy" in blocker for blocker in migration["admission"]["blockers"]
    )
    assert all(not Path(item["path"]).is_absolute() for item in migration["evidence"])


def test_docs_and_generic_tests_do_not_create_a_custom_gate(tmp_path: Path) -> None:
    repo = tmp_path / "docs-only"
    repo.mkdir()
    _write(repo / "README.md", "Migrations, APIs, packages, adapters, and restore drills.\n")
    _write(repo / "tests/test_words.py", "def test_words(): assert 'schema' != 'failure'\n")

    report = audit_ci_gate_candidates(repo, generated_at="2026-08-11T23:30:00+00:00")

    assert report["candidate_count"] == 0
    assert report["candidates"] == []


def test_cli_writes_only_the_explicit_output_artifact(tmp_path: Path) -> None:
    repo = tmp_path / "service"
    _migration_repo(repo)
    output = tmp_path / "candidate-report.json"

    assert (
        main(
            [
                "ci-gate-audit",
                str(repo),
                "--as-of",
                "2026-08-11T23:30:00+00:00",
                "--output",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == CI_GATE_AUDIT_SCHEMA
    assert not (repo / ".quality-runner").exists()


def test_fleet_audit_projects_candidates_into_the_pronto_feed(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "service"
    head = _migration_repo(repo)
    audit = fleet_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "fleet",
        as_of="2026-08-11T23:30:00+00:00",
    )
    artifact_root = Path(str(audit["artifact_root"]))
    replay = fleet_replay_payload(output_dir=artifact_root)
    feed = build_maturity_feed(artifact_root, replay=replay)

    candidate_audit = feed["repositories"][0]["ci_gate_audit"]
    assert replay["status"] == "passed"
    assert candidate_audit["repository"]["head_sha"] == head
    assert candidate_audit["policy"]["authority"] == "recommendation_only"
    assert any(
        candidate["id"] == "custom:migration_compatibility"
        for candidate in candidate_audit["candidates"]
    )
