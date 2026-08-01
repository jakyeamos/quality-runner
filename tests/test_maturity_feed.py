from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quality_runner.fleet.audit import fleet_audit_payload, fleet_replay_payload
from quality_runner.fleet.feed import fleet_feed_payload
from quality_runner.fleet.maturity_feed import (
    MaturityFeedError,
    build_maturity_feed,
    publish_maturity_feed,
    read_maturity_feed,
)


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
    assert first["repositories"][0]["local_identity"]["primary_path"].endswith("/fixture")
    assert any(
        gap["dimension"] == "change_surface_coverage"
        for gap in first["repositories"][0]["dimension_gaps"]
    )
    serialized = json.dumps(first).lower()
    for forbidden in ('"prompt"', '"code"', '"diff"', '"transcript"', '"credential"'):
        assert forbidden not in serialized


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
