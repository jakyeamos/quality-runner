from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quality_runner.fleet.audit import fleet_audit_payload, fleet_replay_payload
from quality_runner.fleet.feed import fleet_feed_payload
from quality_runner.fleet.maturity_feed import (
    MaturityFeedError,
    _repository_projection,
    build_maturity_feed,
    publish_maturity_feed,
    read_maturity_feed,
)


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
    assert first["schema"] == "quality-runner-maturity-feed/v1"
    assert first["repository_count"] == result["repository_count"]
    assert sum(first["quality_outcome_counts"].values()) == first["repository_count"]
    assert first["quality_outcome_taxonomy"]["verification_blocked"]["label"] == (
        "Quality verification blocked"
    )
    assert first["repositories"][0]["local_identity"]["primary_path"].endswith("/fixture")
    assert any(
        gap["dimension"] == "change_surface_coverage"
        for gap in first["repositories"][0]["dimension_gaps"]
    )
    agent_usability = first["repositories"][0]["agent_usability"]
    assert agent_usability["schema"] == "quality-runner-agent-usability/v1"
    assert len(agent_usability["lanes"]) == 4
    assert not any(
        key.startswith("agent_usability.") for key in first["repositories"][0]["dimension_scores"]
    )
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
        "agent_usability.growth_health": 4.0,
        "agent_usability.tool_skill_coverage": 3.0,
    }
    scored = [value for value in repository["dimension_scores"].values() if value is not None]
    assert repository["maturity_score"] == round(sum(scored) / len(scored), 3)
    assert any(
        gap["dimension"] == "agent_usability.behavior_evidence"
        for gap in repository["dimension_gaps"]
    )
    assert result["summary"]["dimension_means"]["agent_usability.behavior_evidence"] == 1.0
    assert feed["mean_maturity"] == result["summary"]["mean_maturity"]


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
    production_after = production_path.read_bytes() if production_path.is_file() else None
    assert production_after == production_before


def test_feed_rejects_failed_replay_and_partial_scope(tmp_path: Path) -> None:
    _, artifact_root = _audit(tmp_path)
    replay = fleet_replay_payload(output_dir=artifact_root)

    failed_replay = {**replay, "status": "failed", "deterministic": False}
    with pytest.raises(MaturityFeedError):
        build_maturity_feed(artifact_root, replay=failed_replay)

    inventory_path = artifact_root / "inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["scope"] = "explicit repository paths under the bounded projects root"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    with pytest.raises(MaturityFeedError):
        build_maturity_feed(artifact_root, replay=replay)


def test_feed_rejects_replay_hash_mismatch(tmp_path: Path) -> None:
    _, artifact_root = _audit(tmp_path)
    replay = fleet_replay_payload(output_dir=artifact_root)
    replay["replayed_summary_hash"] = "not-the-persisted-summary"

    with pytest.raises(MaturityFeedError, match="replay hashes"):
        build_maturity_feed(artifact_root, replay=replay)
