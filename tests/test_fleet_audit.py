from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quality_runner.fleet.audit import (
    fleet_audit_payload,
    fleet_replay_payload,
    fleet_report_payload,
)
from quality_runner.fleet.discovery import (
    repository_record_for_root,
    resolve_target_branch,
)
from quality_runner.fleet.legibility import audit_repository


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _init_repo(root: Path, *, with_quality_command: bool = False) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "dev")
    _git(root, "config", "user.email", "qr-tests@example.com")
    _git(root, "config", "user.name", "Quality Runner Tests")
    (root / "README.md").write_text(
        """# Fixture\n\n## Architecture\nThe repository has a small application boundary.\n\n## Development\nRun tests before completion. Last reviewed: 2026-07-26\n\n## Security\nDo not commit credentials.\n\n## Definition of done\nAcceptance criteria and quality gates pass.\n\n## Deployment\nDeployment uses a release rollback procedure.\n""",
        encoding="utf-8",
    )
    if with_quality_command:
        (root / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n',
            encoding="utf-8",
        )
        (root / "tests").mkdir()
        (root / "tests/test_ok.py").write_text(
            "def test_ok() -> None:\n    assert True\n",
            encoding="utf-8",
        )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")


def test_target_branch_prefers_dev_over_more_advanced_feature(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    _git(root, "branch", "feature")
    _git(root, "switch", "feature")
    (root / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(root, "add", "feature.txt")
    _git(root, "commit", "-m", "feature")
    _git(root, "switch", "dev")

    repository = repository_record_for_root(root)
    target = resolve_target_branch(repository)

    assert target["branch"] == "dev"
    assert target["source"] == "default_dev"
    assert target["status"] == "ready"


def test_static_audit_records_not_applicable_deployment_when_absent(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    repository = repository_record_for_root(root)

    result = audit_repository(
        repository=repository,
        as_of="2026-07-26T17:00:00+00:00",
        run_id="fixture-static",
    )

    findings = {item["dimension"]: item for item in result["findings"]}
    assert findings["architecture_boundaries"]["score"] >= 2
    assert findings["deployment_rollback"]["status"] == "not_applicable"
    assert result["plan"]["local_projection"]["source_edits"] is False


def test_static_audit_scores_structured_legibility_controls_as_maintained() -> None:
    root = Path(__file__).resolve().parents[1]
    repository = repository_record_for_root(root)
    result = audit_repository(
        repository=repository,
        as_of="2026-08-02T05:00:00+00:00",
        run_id="structured-legibility",
    )

    findings = {item["dimension"]: item for item in result["findings"]}
    assert findings["architecture_boundaries"]["status"] == "maintained"
    assert findings["architecture_boundaries"]["score"] == 4
    assert findings["definition_of_done"]["score"] == 4


def test_dynamic_audit_uses_disposable_worktree_and_replays(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    root = projects / "fixture"
    _init_repo(root, with_quality_command=True)
    output = tmp_path / "fleet-output"
    before = _git(root, "status", "--porcelain=v1", "--untracked-files=all")

    first = fleet_audit_payload(
        projects_root=projects,
        output_dir=output,
        dynamic=True,
        as_of="2026-07-26T17:00:00+00:00",
        timeout_seconds=30,
    )

    repo_id = first["summary"]["repository_count"]
    assert repo_id == 1
    assert first["summary"]["dynamic_selected"] == 1
    assert first["summary"]["dynamic_passed"] == 1
    assert _git(root, "status", "--porcelain=v1", "--untracked-files=all") == before
    worktrees = Path(first["artifact_root"]) / "worktrees"
    assert not worktrees.exists() or not any(worktrees.iterdir())

    replay = fleet_replay_payload(output_dir=Path(first["artifact_root"]))
    assert replay["status"] == "passed"
    assert replay["deterministic"] is True

    second = fleet_audit_payload(
        projects_root=projects,
        output_dir=output,
        dynamic=True,
        as_of="2026-07-27T17:00:00+00:00",
        timeout_seconds=30,
    )
    assert second["summary"]["dynamic_reused"] == 1


def test_fleet_replay_is_deterministic_for_multiple_repositories(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    _init_repo(projects / "alpha")
    _init_repo(projects / "beta")
    output = tmp_path / "fleet-output"

    first = fleet_audit_payload(
        projects_root=projects,
        output_dir=output,
        as_of="2026-07-26T17:00:00+00:00",
    )

    assert first["summary"]["repository_count"] == 2
    replay = fleet_replay_payload(output_dir=Path(first["artifact_root"]))

    assert replay["status"] == "passed"
    assert replay["deterministic"] is True


def test_fleet_audit_accepts_a_bounded_repository_slice(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    alpha = projects / "alpha"
    beta = projects / "beta"
    _init_repo(alpha)
    _init_repo(beta)

    audit = fleet_audit_payload(
        projects_root=projects,
        repository_paths=[alpha],
        output_dir=tmp_path / "fleet-output",
        as_of="2026-07-26T17:00:00+00:00",
    )

    assert audit["repository_count"] == 1
    assert audit["summary"]["repository_count"] == 1
    assert audit["summary"]["dynamic_policy"]["changed_only"] is True
    inventory = json.loads((Path(audit["artifact_root"]) / "inventory.json").read_text())
    assert inventory["scope"] == "explicit repository paths under the bounded projects root"


def test_public_report_contains_aggregates_only(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    root = projects / "fixture"
    _init_repo(root)
    output = tmp_path / "fleet-output"
    audit = fleet_audit_payload(
        projects_root=projects,
        output_dir=output,
        as_of="2026-07-26T17:00:00+00:00",
    )

    report = fleet_report_payload(output_dir=Path(audit["artifact_root"]))
    report_text = json.dumps(report)
    assert report["status"] == "review_required"
    assert str(root) not in report_text
    assert "repo-" not in report_text
    assert "raw_prompts" in report_text
    assert report["privacy"]["manual_review_required"] is True
