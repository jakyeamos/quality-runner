from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.fleet.audit import fleet_replay_payload, resolve_artifact_root
from quality_runner.fleet.maturity_feed import (
    DEFAULT_FLEET_ROOT as MATURITY_FEED_FLEET_ROOT,
)
from quality_runner.fleet.maturity_feed import (
    MaturityFeedError,
    build_maturity_feed,
    publish_maturity_feed,
)


def fleet_feed_payload(
    *, audit_id: str | None = None, output_dir: Path | None = None
) -> dict[str, Any]:
    """Validate and publish one immutable fleet audit as the stable maturity feed."""

    if output_dir is not None and _same_path(output_dir, MATURITY_FEED_FLEET_ROOT):
        raise MaturityFeedError(
            "an explicit --output-dir may not point at the production fleet feed root"
        )
    artifact_root = resolve_artifact_root(output_dir, audit_id)
    replay = fleet_replay_payload(output_dir=artifact_root)
    if replay.get("status") != "passed":
        raise MaturityFeedError("fleet audit replay failed; maturity feed was not published")
    feed = build_maturity_feed(
        artifact_root,
        replay=replay,
        expected_projects_root=(Path.home() / "projects") if output_dir is None else None,
    )
    publication_root = (
        MATURITY_FEED_FLEET_ROOT
        if output_dir is None
        else _feed_publication_root(output_dir, artifact_root)
    )
    feed_path = publish_maturity_feed(feed, publication_root)
    return {
        "schema": "quality-runner-maturity-feed-publication/v1",
        "status": "published",
        "audit_id": feed["source"]["audit_id"],
        "artifact_root": str(artifact_root),
        "feed_path": str(feed_path),
        "provenance_hash": feed["provenance_hash"],
        "replay": replay,
        "feed": feed,
        "implementation_allowed": False,
    }


def _feed_publication_root(output_dir: Path, artifact_root: Path) -> Path:
    candidate = output_dir.expanduser()
    try:
        if candidate.resolve() == artifact_root.resolve():
            return candidate.parent
    except OSError:
        pass
    return candidate


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.expanduser().resolve() == right.expanduser().resolve()
    except OSError:
        return False
