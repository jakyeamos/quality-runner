from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quality_runner.fleet.audit import (
    _static_scan_repository,
    fleet_audit_payload,
    fleet_replay_payload,
    fleet_report_payload,
)
from quality_runner.fleet.discovery import (
    repository_record_for_root,
    resolve_target_branch,
)
from quality_runner.fleet.legibility import audit_repository
from quality_runner.fleet.projection import build_local_projection
from quality_runner.fleet.summary import build_fleet_summary


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


def test_static_scan_uses_ready_target_checkout_without_replacing_identity() -> None:
    repository = {
        "repo_id": "repo-example",
        "primary_path": "/projects/repository",
        "checkouts": [
            {
                "checkout_id": "checkout-dev",
                "path": "/private/tmp/repository-dev",
                "branch": "dev",
                "dirty": False,
                "exists": True,
            }
        ],
        "target_branch": {
            "branch": "dev",
            "checkout_id": "checkout-dev",
            "status": "ready",
        },
    }

    scanned = _static_scan_repository(repository)

    assert scanned["primary_path"] == "/private/tmp/repository-dev"
    assert scanned["repo_id"] == repository["repo_id"]
    assert repository["primary_path"] == "/projects/repository"


def test_static_scan_preserves_identity_for_unusable_target_metadata() -> None:
    assert _static_scan_repository({"primary_path": "/projects/repository"}) == {
        "primary_path": "/projects/repository"
    }
    assert _static_scan_repository({"target_branch": {"status": "ready"}}) == {
        "target_branch": {"status": "ready"}
    }
    assert _static_scan_repository({"target_branch": {"status": "ready", "checkout_id": 7}}) == {
        "target_branch": {"status": "ready", "checkout_id": 7}
    }
    assert (
        _static_scan_repository(
            {
                "target_branch": {"status": "ready", "checkout_id": "checkout-dev"},
                "checkouts": [{"checkout_id": "other", "path": "/private/tmp/other"}],
            }
        )["target_branch"]["checkout_id"]
        == "checkout-dev"
    )
    assert _static_scan_repository(
        {
            "target_branch": {"status": "ready", "checkout_id": "checkout-dev"},
            "checkouts": [{"checkout_id": "checkout-dev", "path": None}],
        }
    ) == {
        "target_branch": {"status": "ready", "checkout_id": "checkout-dev"},
        "checkouts": [{"checkout_id": "checkout-dev", "path": None}],
    }


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


def test_projection_handles_unscored_applicable_findings() -> None:
    projection = build_local_projection(
        {"repo_id": "repo-example"},
        [
            {
                "dimension": "architecture_boundaries",
                "status": "unknown",
                "score": None,
            },
            {
                "dimension": "deployment_rollback",
                "status": "not_applicable",
                "score": None,
            },
        ],
    )

    assert "architecture and boundaries" in projection["content"]
    assert "deployment and rollback" not in projection["content"]


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
    assert replay["manifest_valid"] is True

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
    assert replay["manifest_valid"] is True


def test_fleet_replay_rejects_a_tampered_finding_even_when_summary_is_unchanged(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    _init_repo(projects / "fixture")
    first = fleet_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "fleet-output",
        as_of="2026-07-26T17:00:00+00:00",
    )
    artifact_root = Path(first["artifact_root"])
    finding_path = next((artifact_root / "findings").glob("*.json"))
    finding = json.loads(finding_path.read_text(encoding="utf-8"))
    finding["tampered_without_summary_effect"] = True
    finding_path.write_text(json.dumps(finding), encoding="utf-8")

    replay = fleet_replay_payload(output_dir=artifact_root)

    assert replay["status"] == "failed"
    assert replay["deterministic"] is False
    assert replay["manifest_valid"] is False
    assert replay["manifest_errors"] == ["finding hashes mismatch"]


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
    assert inventory["dynamic_policy"]["repository_watchdog_timeout_seconds"] == 1170


def test_scope_manifest_attests_an_exact_population_and_preserves_exclusions(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    alpha = projects / "alpha"
    deprecated = projects / "deprecated"
    _init_repo(alpha)
    _init_repo(deprecated)
    manifest = tmp_path / "fleet-scope.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "quality-runner-fleet-scope/v1",
                "authority": "fixture registry with owner-reviewed exclusions",
                "generated_at": "2026-08-15T15:00:00+00:00",
                "repositories": [
                    {
                        "path": str(alpha),
                        "eligibility": "eligible",
                        "reason": "registered and active",
                    },
                    {
                        "path": str(deprecated),
                        "eligibility": "excluded",
                        "reason": "deprecated by the repository owner",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    audit = fleet_audit_payload(
        projects_root=projects,
        scope_manifest=manifest,
        output_dir=tmp_path / "fleet-output",
        as_of="2026-08-15T15:01:00+00:00",
    )

    assert audit["repository_count"] == 1
    coverage = audit["summary"]["population_coverage"]
    assert coverage["status"] == "complete"
    assert coverage["source"] == "scope_manifest"
    assert coverage["expected_repository_count"] == 1
    assert coverage["observed_repository_count"] == 1
    assert coverage["excluded_repository_count"] == 1
    inventory = json.loads((Path(audit["artifact_root"]) / "inventory.json").read_text())
    assert inventory["scope"] == "complete repository population from a validated scope manifest"


def test_scope_manifest_rejects_duplicate_and_out_of_root_paths(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    alpha = projects / "alpha"
    outside = tmp_path / "outside"
    _init_repo(alpha)
    _init_repo(outside)
    manifest = tmp_path / "fleet-scope.json"
    base = {
        "schema": "quality-runner-fleet-scope/v1",
        "authority": "fixture registry",
        "generated_at": "2026-08-15T15:00:00+00:00",
    }
    manifest.write_text(
        json.dumps(
            {
                **base,
                "repositories": [
                    {"path": str(alpha), "eligibility": "eligible", "reason": "active"},
                    {"path": str(alpha), "eligibility": "excluded", "reason": "duplicate"},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicated"):
        fleet_audit_payload(projects_root=projects, scope_manifest=manifest)

    manifest.write_text(
        json.dumps(
            {
                **base,
                "repositories": [
                    {"path": str(outside), "eligibility": "eligible", "reason": "outside"}
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="outside projects_root"):
        fleet_audit_payload(projects_root=projects, scope_manifest=manifest)


def test_measurement_confidence_requires_population_static_dynamic_and_gap_coverage() -> None:
    repository = {
        "repo_id": "repo-fixture",
        "repository": {"checkout_count": 1},
        "findings": [
            {
                "dimension": "quality_commands",
                "status": "maintained",
                "score": 4,
                "priority": "P2",
            }
        ],
        "agent_usability": {"applicability": "not_applicable"},
        "dynamic": {"selected": True, "status": "passed"},
    }
    coverage = {
        "status": "complete",
        "source": "scope_manifest",
        "expected_repository_count": 1,
        "observed_repository_count": 1,
        "excluded_repository_count": 0,
    }

    high = build_fleet_summary(
        audit_id="audit-high",
        as_of="2026-08-15T15:00:00+00:00",
        repositories=[repository],
        dynamic=True,
        changed_only=False,
        population_coverage=coverage,
    )
    static_only = build_fleet_summary(
        audit_id="audit-medium",
        as_of="2026-08-15T15:00:00+00:00",
        repositories=[repository],
        dynamic=False,
        changed_only=True,
        population_coverage=coverage,
    )

    assert high["confidence"] == "high"
    assert high["confidence_limitations"] == []
    assert high["confidence_basis"] == [
        "complete_population",
        "complete_static_scan",
        "complete_dynamic_verification",
        "no_unresolved_measurement_gaps",
    ]
    assert static_only["confidence"] == "medium"
    assert static_only["confidence_limitations"] == ["dynamic_verification_disabled"]


def test_conclusive_dynamic_failure_does_not_masquerade_as_a_measurement_gap() -> None:
    summary = build_fleet_summary(
        audit_id="audit-known-failure",
        as_of="2026-08-15T15:00:00+00:00",
        repositories=[
            {
                "repo_id": "repo-fixture",
                "repository": {"checkout_count": 1},
                "findings": [
                    {
                        "dimension": "dynamic_verification",
                        "status": "blocked",
                        "score": 0,
                        "priority": "P0",
                    }
                ],
                "agent_usability": {"applicability": "not_applicable"},
                "dynamic": {"selected": True, "status": "failed"},
            }
        ],
        dynamic=True,
        changed_only=False,
        population_coverage={
            "status": "complete",
            "source": "scope_manifest",
            "expected_repository_count": 1,
            "observed_repository_count": 1,
            "excluded_repository_count": 0,
        },
    )

    assert summary["confidence"] == "high"
    assert summary["dynamic_failed"] == 1
    assert summary["unresolved_measurement_gaps"] == []


def test_conclusive_low_static_states_do_not_masquerade_as_measurement_gaps() -> None:
    summary = build_fleet_summary(
        audit_id="audit-known-low",
        as_of="2026-08-15T15:00:00+00:00",
        repositories=[
            {
                "repo_id": "repo-fixture",
                "repository": {"checkout_count": 1},
                "findings": [
                    {
                        "dimension": "behavior_assurance",
                        "status": "unknown",
                        "score": 0,
                        "applicable": True,
                        "priority": "P0",
                    },
                    {
                        "dimension": "context_routing",
                        "status": "stale",
                        "score": 2,
                        "applicable": True,
                        "priority": "P1",
                    },
                    {
                        "dimension": "architecture_boundaries",
                        "status": "blocked",
                        "score": 1,
                        "applicable": True,
                        "priority": "P1",
                    },
                ],
                "agent_usability": {"applicability": "not_applicable"},
                "dynamic": {"selected": True, "status": "failed"},
            }
        ],
        dynamic=True,
        changed_only=False,
        population_coverage={
            "status": "complete",
            "source": "scope_manifest",
            "expected_repository_count": 1,
            "observed_repository_count": 1,
            "excluded_repository_count": 0,
        },
    )

    assert summary["confidence"] == "high"
    assert summary["unresolved_measurement_gaps"] == []


def test_unknown_applicability_without_a_numeric_score_is_a_measurement_gap() -> None:
    summary = build_fleet_summary(
        audit_id="audit-unknown-applicability",
        as_of="2026-08-15T15:00:00+00:00",
        repositories=[
            {
                "repo_id": "repo-fixture",
                "repository": {"checkout_count": 1},
                "findings": [
                    {
                        "dimension": "license_contribution",
                        "status": "unknown",
                        "score": None,
                        "applicable": None,
                        "priority": "P1",
                    }
                ],
                "agent_usability": {"applicability": "not_applicable"},
                "dynamic": {"selected": True, "status": "passed"},
            }
        ],
        dynamic=True,
        changed_only=False,
        population_coverage={
            "status": "complete",
            "source": "scope_manifest",
            "expected_repository_count": 1,
            "observed_repository_count": 1,
            "excluded_repository_count": 0,
        },
    )

    assert summary["confidence"] == "medium"
    assert summary["unresolved_measurement_gaps"] == [
        "repo-fixture:license_contribution:unknown"
    ]


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
