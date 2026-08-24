from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quality_runner.fleet import feed as feed_module
from quality_runner.fleet.audit import fleet_audit_payload, fleet_replay_payload
from quality_runner.fleet.contracts import digest
from quality_runner.fleet.feed import fleet_feed_payload
from quality_runner.fleet.maturity_checkpoint import _qr_target_commits
from quality_runner.fleet.maturity_coverage import (
    AuditCoverageFeedError,
    validate_feed_audit_coverage,
)
from quality_runner.fleet.maturity_feed import (
    MaturityFeedError,
    _repository_projection,
    build_maturity_feed,
    publish_maturity_feed,
    read_maturity_feed,
)


def test_coverage_validation_accepts_legacy_v1_only_when_metadata_is_wholly_absent() -> None:
    repositories = [{"repo_id": "legacy"}]

    validate_feed_audit_coverage({}, repositories)

    with pytest.raises(AuditCoverageFeedError, match="partially present"):
        validate_feed_audit_coverage(
            {"audit_coverage": {"policy": "require_complete"}}, repositories
        )


def test_checkpoint_binds_qr_canonical_target_not_primary_worktree() -> None:
    inventory = {
        "repositories": [
            {
                "repo_id": "repo-1",
                "primary_path": "/projects/repo-1",
                "target_branch": {
                    "branch": "dev",
                    "checkout_id": "checkout-dev",
                    "status": "ready",
                    "head": "canonical-target",
                },
                "checkouts": [
                    {
                        "checkout_id": "checkout-feature",
                        "is_primary": True,
                        "head": "unfolded-feature",
                    },
                    {
                        "checkout_id": "checkout-dev",
                        "is_primary": False,
                        "head": "canonical-target",
                    },
                ],
            }
        ]
    }

    assert _qr_target_commits(inventory) == {"repo-1": "canonical-target"}


def test_blocked_dynamic_finding_and_target_evidence_reach_feed_projection() -> None:
    target_state = {
        "status": "stale",
        "reason": "target branch is behind its configured upstream",
        "local_head": "abc",
        "upstream": "origin/dev",
        "upstream_head": "def",
        "ahead": 0,
        "behind": 1,
        "safe_action": "fast_forward_local_target",
    }
    repository = {
        "repo_id": "repo-1",
        "primary_path": "/projects/repo-1",
        "target_branch": {
            "branch": "dev",
            "status": "stale",
            "head": "abc",
            "target_state": target_state,
        },
    }
    finding = {
        "repo_id": "repo-1",
        "findings": [
            {
                "dimension": "dynamic_verification",
                "status": "blocked",
                "score": 0,
                "severity": "high",
                "priority": "P0",
                "message": "Dynamic verification is blocked.",
            }
        ],
        "dynamic": {"status": "blocked"},
        "agent_usability": {},
    }

    projection = _repository_projection(repository, finding)

    assert projection["quality_status"] == "blocked"
    assert projection["quality_outcome"] == {
        "state": "verification_blocked",
        "label": "Quality verification blocked",
        "disposition": "No trustworthy verdict was produced because verification is blocked. Repair setup or target provenance, then rerun it.",
        "next_step": "Repair the setup or target provenance, then rerun the blocked verification and fleet audit.",
    }
    assert projection["blocker_count"] == 1
    assert projection["dynamic_status"] == "blocked"
    assert projection["target_state"] == target_state
    assert projection["repository_maturity"]["critical_cap"]["applied"] is False


def test_only_confirmed_critical_risk_caps_repository_maturity() -> None:
    repository = {
        "repo_id": "repo-1",
        "primary_path": "/projects/repo-1",
        "target_branch": {"branch": "dev", "status": "ready", "head": "abc"},
    }
    finding = {
        "repo_id": "repo-1",
        "findings": [
            {
                "dimension": "security_constraints",
                "status": "blocked",
                "score": 4,
                "severity": "blocker",
                "priority": "P0",
                "applicability": "applicable",
                "confirmed_critical_risk": True,
                "message": "A confirmed critical risk is present.",
            }
        ],
        "dynamic": {"status": "not_selected"},
        "agent_usability": {"applicability": "not_applicable"},
    }

    projection = _repository_projection(repository, finding)

    assert projection["repository_maturity"]["uncapped_score"] == 4
    assert projection["repository_maturity"]["score"] == 2
    assert projection["repository_maturity"]["critical_cap"]["applied"] is True


def test_feed_projection_preserves_current_and_future_finding_dimensions() -> None:
    dimensions = [f"dimension_{index:02d}" for index in range(20)] + ["future_dimension"]
    projection = _repository_projection(
        {
            "repo_id": "repo-1",
            "primary_path": "/projects/repo-1",
            "target_branch": {"branch": "dev", "status": "ready", "head": "abc"},
        },
        {
            "repo_id": "repo-1",
            "findings": [
                {
                    "dimension": dimension,
                    "status": "discoverable",
                    "score": 2,
                    "severity": "observation",
                    "priority": "P1",
                    "message": f"{dimension} needs maintained evidence.",
                }
                for dimension in dimensions
            ],
            "dynamic": {"status": "not_selected"},
            "agent_usability": {},
        },
    )

    assert set(projection["dimension_scores"]) == set(dimensions)
    assert {gap["dimension"] for gap in projection["dimension_gaps"]} == set(dimensions)


def test_cache_design_projection_preserves_state_without_publishing_paths() -> None:
    projection = _repository_projection(
        {
            "repo_id": "repo-1",
            "primary_path": "/projects/repo-1",
            "target_branch": {"branch": "dev", "status": "ready", "head": "abc"},
        },
        {
            "repo_id": "repo-1",
            "findings": [
                {
                    "dimension": "cache_design",
                    "status": "unknown",
                    "applicability": "unknown",
                    "score": None,
                    "severity": "observation",
                    "priority": "P1",
                    "message": "Traversal was incomplete.",
                    "evidence": [
                        {
                            "schema": "quality-runner-cache-design-assessment-v1",
                            "status": "unknown",
                            "score": None,
                            "measurement_complete": False,
                            "totals": {"allocated_bytes": 4096, "file_count": 1},
                            "categories": {
                                "tool_cache": {"allocated_bytes": 4096, "file_count": 1}
                            },
                            "risk_flags": ["measurement_incomplete"],
                            "growth": {"available": False, "snapshot_count": 0},
                            "surfaces": [{"path": ".private/cache"}],
                        }
                    ],
                }
            ],
            "dynamic": {"status": "not_selected"},
            "agent_usability": {},
        },
    )

    assert projection["cache_design"]["status"] == "unknown"
    assert projection["cache_design"]["categories"]["tool_cache"]["allocated_bytes"] == 4096
    assert "surfaces" not in projection["cache_design"]
    assert ".private/cache" not in json.dumps(projection["cache_design"])


@pytest.mark.parametrize(
    ("dynamic_status", "finding_status", "priority", "dimension", "expected_code"),
    [
        ("failed", "blocked", "P0", "dynamic_verification", "checks_failing"),
        ("timeout", "blocked", "P0", "dynamic_verification", "verification_blocked"),
        ("blocked", "blocked", "P0", "dynamic_verification", "verification_blocked"),
        ("unknown", "unknown", "P1", "dynamic_verification", "evidence_unknown"),
        ("reused", "blocked", "P0", "dependency_health", "checks_failing"),
        ("not_selected", "maintained", "P2", "dependency_health", "review_needed"),
        ("reused", "maintained", "P2", "dependency_health", "healthy"),
    ],
)
def test_quality_outcome_distinguishes_failure_from_verification_blockage(
    dynamic_status: str,
    finding_status: str,
    priority: str,
    dimension: str,
    expected_code: str,
) -> None:
    projection = _repository_projection(
        {
            "repo_id": "repo-1",
            "primary_path": "/projects/repo-1",
            "target_branch": {"branch": "dev", "status": "ready", "head": "abc"},
        },
        {
            "repo_id": "repo-1",
            "findings": [
                {
                    "dimension": dimension,
                    "status": finding_status,
                    "score": 4 if finding_status == "maintained" else 0,
                    "severity": "high" if priority == "P0" else "observation",
                    "priority": priority,
                    "message": "Fixture evidence.",
                }
            ],
            "dynamic": {"status": dynamic_status},
            "agent_usability": {},
        },
    )

    assert projection["quality_outcome"]["state"] == expected_code


def test_quality_outcome_disposition_names_review_dimensions() -> None:
    projection = _repository_projection(
        {
            "repo_id": "repo-1",
            "primary_path": "/projects/repo-1",
            "target_branch": {"branch": "dev", "status": "ready", "head": "abc"},
        },
        {
            "repo_id": "repo-1",
            "findings": [
                {
                    "dimension": "change_surface_coverage",
                    "status": "maintained",
                    "score": 3,
                    "severity": "observation",
                    "priority": "P2",
                    "message": "The change matrix is discoverable but not current.",
                }
            ],
            "dynamic": {"status": "not_selected"},
            "agent_usability": {},
        },
    )

    disposition = projection["quality_outcome"]["disposition"]
    assert projection["quality_outcome"]["state"] == "review_needed"
    assert "change-surface coverage" in disposition
    assert "[maintained, score 3]" in disposition
    assert "The change matrix is discoverable but not current." in disposition
    assert "not a failing-test result" in disposition


def test_quality_outcome_disposition_keeps_unknown_separate_from_failure() -> None:
    projection = _repository_projection(
        {
            "repo_id": "repo-1",
            "primary_path": "/projects/repo-1",
            "target_branch": {"branch": "dev", "status": "ready", "head": "abc"},
        },
        {
            "repo_id": "repo-1",
            "findings": [
                {
                    "dimension": "quality_commands",
                    "status": "unknown",
                    "score": None,
                    "severity": "observation",
                    "priority": "P1",
                    "message": "Current quality command evidence is unavailable.",
                }
            ],
            "dynamic": {"status": "not_selected"},
            "agent_usability": {},
        },
    )

    outcome = projection["quality_outcome"]
    disposition = outcome["disposition"]
    assert outcome["state"] == "evidence_unknown"
    assert outcome["label"] == "Evidence review required"
    assert "quality commands [not confirmed, score n/a]" in disposition
    assert "Current quality command evidence is unavailable." in disposition
    assert "not a failing-test result" in disposition
    assert "unknown" not in disposition.lower()
    assert "Identify the listed evidence gaps" in outcome["next_step"]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "dev")
    _git(root, "config", "user.email", "qr-feed-tests@example.com")
    _git(root, "config", "user.name", "Quality Runner Feed Tests")
    (root / "README.md").write_text(
        """# Feed fixture

## Architecture
The fixture has one application boundary.

## Development
Run the test command before completion. Last reviewed: 2026-07-26

## Security
Do not commit credentials.

## Definition of done
Acceptance criteria and quality gates pass.

## Deployment
Deployment has a rollback procedure.
""",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")


def _add_agent_surface(root: Path) -> None:
    router = root / ".agents/context/README.md"
    commands = root / ".agents/context/commands.md"
    skill = root / ".agents/skills/example/SKILL.md"
    manifest = root / ".agents/agent-usability.json"
    for path in (router, commands, skill, manifest):
        path.parent.mkdir(parents=True, exist_ok=True)
    router.write_text("[Commands](commands.md)\n", encoding="utf-8")
    commands.write_text("# Agent command\n", encoding="utf-8")
    skill.write_text(
        "---\nname: example\ndescription: Use the example agent command.\n---\n",
        encoding="utf-8",
    )
    manifest.write_text(
        json.dumps(
            {
                "schema": "agent-usability/v1",
                "reviewed_at": "2026-07-26",
                "tools": [
                    {
                        "id": "example-cli",
                        "documentation": [".agents/context/commands.md"],
                        "skills": ["example"],
                        "behavior_evidence": [],
                    }
                ],
                "skills": [
                    {
                        "id": "example",
                        "family": "repository-operations",
                        "source": "hosted",
                        "contract_path": ".agents/skills/example/SKILL.md",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _git(root, "add", ".agents")
    _git(root, "commit", "-m", "add agent surface")


def _audit(tmp_path: Path) -> tuple[dict[str, object], Path]:
    projects = tmp_path / "projects"
    _init_repo(projects / "fixture")
    result = fleet_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "fleet",
        as_of="2026-07-26T17:00:00+00:00",
    )
    return result, Path(str(result["artifact_root"]))


def test_feed_is_deterministic_and_redacted(tmp_path: Path) -> None:
    result, artifact_root = _audit(tmp_path)
    replay = fleet_replay_payload(output_dir=artifact_root)

    first = build_maturity_feed(artifact_root, replay=replay)
    second = build_maturity_feed(artifact_root, replay=replay)

    assert replay["status"] == "passed"
    assert first == second
    assert first["schema"] == "quality-runner-maturity-feed/v2"
    assert first["measurement_confidence"]["level"] == "medium"
    assert first["measurement_confidence"]["deterministic_replay"] is True
    assert "dynamic_verification_disabled" in first["measurement_confidence"]["limitations"]
    assert first["repository_count"] == result["repository_count"]
    assert first["audit_coverage"] == {
        "status": "complete",
        "policy": "require_complete",
        "complete_repository_count": 1,
        "incomplete_repository_count": 0,
        "comparison_eligible": True,
        "canonical_findings_scope": "exact_target_heads",
    }
    assert first["repositories"][0]["audit_coverage"]["status"] == "complete"
    assert first["repositories"][0]["comparison_eligible"] is True
    assert sum(first["quality_outcome_counts"].values()) == first["repository_count"]
    assert first["quality_outcome_taxonomy"]["verification_blocked"]["label"] == (
        "Quality verification blocked"
    )
    assert first["repositories"][0]["local_identity"]["primary_path"].endswith("/fixture")
    assert any(
        gap["dimension"] == "change_surface_coverage"
        for gap in first["repositories"][0]["dimension_gaps"]
    )
    assert "matrix_maintenance" in first["repositories"][0]["dimension_scores"]
    assert any(
        gap["dimension"] == "matrix_maintenance"
        for gap in first["repositories"][0]["dimension_gaps"]
    )
    agent_usability = first["repositories"][0]["agent_usability"]
    assert agent_usability["schema"] == "quality-runner-agent-usability/v1"
    assert agent_usability["applicability"] == "not_applicable"
    assert len(agent_usability["lanes"]) == 4
    behavior_assurance = first["repositories"][0]["behavior_assurance"]
    assert behavior_assurance["schema"] == "quality-runner-behavior-assurance/v2"
    assert behavior_assurance["contract_status"] == "missing"
    assert behavior_assurance["release_ready"] is False
    assert first["behavior_assurance"] == {
        "schema": "quality-runner-behavior-assurance-summary/v2",
        "status": "gaps_present",
        "repository_count": 1,
        "ready_repository_count": 0,
        "applicability_counts": {"unknown": 1},
        "result_status_counts": {"unknown": 1},
        "contract_schema_counts": {"missing": 1},
        "edge_profile_status_counts": {"missing": 1},
        "state_counts": {"missing_contract": 1},
        "required_scenario_count": 0,
        "passed_scenario_count": 0,
        "gap_count": 1,
        "coverage": {
            "total": 0,
            "profiled": 0,
            "verified": 0,
            "stale": 0,
            "failed": 0,
            "blocked": 0,
            "unknown": 0,
        },
    }
    assert not any(
        key.startswith("agent_usability.") for key in first["repositories"][0]["dimension_scores"]
    )
    repository_maturity = first["repositories"][0]["repository_maturity"]
    assert repository_maturity["schema"] == "quality-runner-repository-maturity/v2"
    assert len(repository_maturity["pillars"]) == 7
    assert repository_maturity["evidence"]["unknown_applicability"] == []
    assert first["mean_maturity"] == repository_maturity["score"]
    assert first["source_dimension_mean"] == result["summary"]["mean_maturity"]
    serialized = json.dumps(first).lower()
    for forbidden in ('"prompt"', '"code"', '"diff"', '"transcript"', '"credential"'):
        assert forbidden not in serialized


def test_agent_usability_scores_contribute_to_repository_and_fleet_maturity(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    root = projects / "fixture"
    _init_repo(root)
    _add_agent_surface(root)
    result = fleet_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "fleet",
        as_of="2026-07-26T17:00:00+00:00",
    )
    artifact_root = Path(str(result["artifact_root"]))
    feed = build_maturity_feed(
        artifact_root,
        replay=fleet_replay_payload(output_dir=artifact_root),
    )

    repository = feed["repositories"][0]
    agent_dimensions = {
        key: value
        for key, value in repository["dimension_scores"].items()
        if key.startswith("agent_usability.")
    }
    assert agent_dimensions == {
        "agent_usability.behavior_evidence": 1.0,
        "agent_usability.documentation_contract": 4.0,
        "agent_usability.freshness_portability": 3.0,
        "agent_usability.tool_skill_coverage": 3.0,
    }
    model = repository["repository_maturity"]
    assert repository["maturity_score"] == model["score"]
    assert repository["source_dimension_mean"] != repository["maturity_score"]
    assert {pillar["id"] for pillar in model["pillars"]} == {
        "correctness_reliability",
        "security_privacy_supply_chain",
        "maintainability_evolvability",
        "operability_release_safety",
        "user_facing_quality",
        "human_agent_usability",
        "governance_sustainability",
    }
    assert (
        next(pillar for pillar in model["pillars"] if pillar["id"] == "human_agent_usability")[
            "score"
        ]
        == 2.125
    )
    assert any(
        gap["dimension"] == "agent_usability.behavior_evidence"
        for gap in repository["dimension_gaps"]
    )
    assert result["summary"]["dimension_means"]["agent_usability.behavior_evidence"] == 1.0
    assert feed["source_dimension_mean"] == result["summary"]["mean_maturity"]


def test_feed_publish_replaces_stable_file_atomically(tmp_path: Path) -> None:
    _, artifact_root = _audit(tmp_path)
    replay = fleet_replay_payload(output_dir=artifact_root)
    feed = build_maturity_feed(artifact_root, replay=replay)

    feed_path = publish_maturity_feed(feed, tmp_path / "runtime")

    assert feed_path == tmp_path / "runtime" / "current" / "maturity.json"
    assert read_maturity_feed(feed_path) == feed
    assert not list(feed_path.parent.glob(".maturity-*.tmp"))


def test_feed_command_publishes_to_an_override_without_touching_production(tmp_path: Path) -> None:
    _, artifact_root = _audit(tmp_path)
    production_path = Path.home() / ".quality-runner" / "fleet-audit" / "current" / "maturity.json"
    production_before = production_path.read_bytes() if production_path.is_file() else None

    result = fleet_feed_payload(output_dir=artifact_root)

    assert result["status"] == "published"
    assert result["feed_path"] == str(tmp_path / "fleet" / "current" / "maturity.json")
    assert result["checkpoint"]["schema"] == "quality-runner-maturity-checkpoint/v1"
    assert Path(str(result["checkpoint_path"])).is_file()
    checkpoint = json.loads(Path(str(result["checkpoint_path"])).read_text(encoding="utf-8"))
    assert checkpoint["status"] == "complete"
    assert checkpoint["components"]["qr_maturity"]["audit_id"] == result["audit_id"]
    assert checkpoint["target"]["repository_count"] == result["feed"]["repository_count"]
    production_after = production_path.read_bytes() if production_path.is_file() else None
    assert production_after == production_before


def test_feed_rejects_mixed_qr_and_mac_control_commits(tmp_path: Path) -> None:
    _, artifact_root = _audit(tmp_path)
    mac_inventory_path = next((artifact_root / "mac-control").glob("*/inventory.json"))
    mac_inventory = json.loads(mac_inventory_path.read_text(encoding="utf-8"))
    mac_inventory["repositories"][0]["observed_commit"] = "not-the-qr-commit"
    mac_inventory_path.write_text(json.dumps(mac_inventory), encoding="utf-8")

    with pytest.raises(MaturityFeedError, match="observed commits"):
        fleet_feed_payload(output_dir=artifact_root)


def test_feed_does_not_downgrade_a_blocked_coordinated_lane_to_legacy(tmp_path: Path) -> None:
    _, artifact_root = _audit(tmp_path)
    checkpoint_path = artifact_root / "maturity-checkpoint.json"
    checkpoint = {
        "status": "blocked",
        "reason": "Mac Control lane could not be created",
    }
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    mac_control_root = artifact_root / "mac-control"
    (next(mac_control_root.glob("*/inventory.json"))).unlink()

    with pytest.raises(MaturityFeedError, match="coordinated Mac Control lane is blocked"):
        fleet_feed_payload(output_dir=artifact_root)


def test_feed_command_accepts_an_explicit_external_production_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result, artifact_root = _audit(tmp_path)
    projects_root = tmp_path / "projects"
    production_root = tmp_path / "production-feed"
    monkeypatch.setattr(feed_module, "MATURITY_FEED_FLEET_ROOT", production_root)
    monkeypatch.setattr(
        feed_module,
        "resolve_artifact_root",
        lambda output_dir, audit_id: artifact_root,
    )

    published = fleet_feed_payload(
        audit_id=str(result["audit_id"]),
        production_projects_root=projects_root,
    )

    assert published["status"] == "published"
    assert published["feed_path"] == str(production_root / "current" / "maturity.json")
    assert published["feed"]["source"]["projects_root"] == str(projects_root.resolve())


def test_feed_command_still_rejects_a_partial_external_scope(tmp_path: Path) -> None:
    result, artifact_root = _audit(tmp_path)
    inventory_path = artifact_root / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["scope"] = "explicit repository paths under the bounded projects root"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    manifest_path = artifact_root / "replay-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads((artifact_root / "summary.json").read_text(encoding="utf-8"))
    manifest["inventory_hash"] = digest(inventory)
    manifest["provenance_hash"] = digest({"inventory": inventory, "summary": summary})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(MaturityFeedError, match="fleet-wide audit scope"):
        fleet_feed_payload(
            audit_id=str(result["audit_id"]),
            output_dir=artifact_root,
            production_projects_root=tmp_path / "projects",
        )


def test_feed_rejects_failed_replay_and_partial_scope(tmp_path: Path) -> None:
    _, artifact_root = _audit(tmp_path)
    replay = fleet_replay_payload(output_dir=artifact_root)

    failed_replay = {**replay, "status": "failed", "deterministic": False}
    with pytest.raises(MaturityFeedError):
        build_maturity_feed(artifact_root, replay=failed_replay)

    summary_path = artifact_root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["population_coverage"]["status"] = "bounded"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(MaturityFeedError):
        build_maturity_feed(artifact_root, replay=replay)


def test_feed_requires_complete_fold_coverage_unless_diagnostic_override_is_explicit(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    root = projects / "fixture"
    _init_repo(root)
    _git(root, "switch", "-c", "feature")
    (root / "feature.txt").write_text("feature\n", encoding="utf-8")
    _git(root, "add", "feature.txt")
    _git(root, "commit", "-m", "feature")
    _git(root, "switch", "dev")
    result = fleet_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "fleet",
        as_of="2026-07-26T17:00:00+00:00",
    )
    artifact_root = Path(str(result["artifact_root"]))
    replay = fleet_replay_payload(output_dir=artifact_root)

    with pytest.raises(MaturityFeedError, match="complete canonical audit coverage"):
        build_maturity_feed(artifact_root, replay=replay)

    feed = build_maturity_feed(
        artifact_root,
        replay=replay,
        allow_incomplete_coverage=True,
    )

    assert feed["audit_coverage"] == {
        "status": "incomplete",
        "policy": "allow_incomplete",
        "complete_repository_count": 0,
        "incomplete_repository_count": 1,
        "comparison_eligible": False,
        "canonical_findings_scope": "exact_target_heads",
    }
    repository = feed["repositories"][0]
    assert repository["audit_coverage"]["status"] == "incomplete_unfolded"
    assert repository["comparison_eligible"] is False
    assert repository["maturity_status"] != "certified"

    publication = fleet_feed_payload(
        output_dir=artifact_root,
        allow_incomplete_coverage=True,
    )
    assert publication["status"] == "published"
    assert publication["feed"]["audit_coverage"]["comparison_eligible"] is False


def test_feed_rejects_replay_hash_mismatch(tmp_path: Path) -> None:
    _, artifact_root = _audit(tmp_path)
    replay = fleet_replay_payload(output_dir=artifact_root)
    replay["replayed_summary_hash"] = "not-the-persisted-summary"

    with pytest.raises(MaturityFeedError, match="replay hashes"):
        build_maturity_feed(artifact_root, replay=replay)
