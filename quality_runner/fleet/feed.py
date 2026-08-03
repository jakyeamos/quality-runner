from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_runner.fleet.audit import fleet_replay_payload, resolve_artifact_root
from quality_runner.fleet.mac_control_artifacts import (
    mac_control_replay_payload,
    read_object,
)
from quality_runner.fleet.maturity_checkpoint import (
    MaturityCheckpointError,
    publish_maturity_checkpoint,
)
from quality_runner.fleet.maturity_feed import (
    DEFAULT_FLEET_ROOT as MATURITY_FEED_FLEET_ROOT,
)
from quality_runner.fleet.maturity_feed import (
    MaturityFeedError,
    build_maturity_feed,
    publish_maturity_feed,
)


def fleet_feed_payload(
    *,
    audit_id: str | None = None,
    output_dir: Path | None = None,
    allow_incomplete_coverage: bool = False,
    production_projects_root: Path | None = None,
) -> dict[str, Any]:
    """Validate and publish one immutable fleet audit as the stable maturity feed.

    The default publication scope is ``~/projects``. A caller may explicitly
    authorize another bounded projects root for a canonical feed publication;
    the immutable snapshot must still cover every repository identity under
    that root and pass deterministic replay.
    """

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
        expected_projects_root=(
            production_projects_root.expanduser().resolve()
            if production_projects_root is not None
            else (Path.home() / "projects")
            if output_dir is None
            else None
        ),
        allow_incomplete_coverage=allow_incomplete_coverage,
    )
    publication_root = (
        MATURITY_FEED_FLEET_ROOT
        if output_dir is None
        else _feed_publication_root(output_dir, artifact_root)
    )
    checkpoint_path: Path | None = None
    checkpoint: dict[str, Any] = {
        "status": "legacy_uncoordinated",
        "reason": "the QR audit did not contain its coordinated Mac Control lane",
    }
    mac_control_root = _mac_control_artifact_root(artifact_root)
    if mac_control_root is not None:
        mac_control_inventory = read_object(mac_control_root / "inventory.json")
        mac_control_report = read_object(mac_control_root / "mac-control-ideal-state.json")
        mac_control_summary = read_object(mac_control_root / "summary.json")
        mac_control_replay = mac_control_replay_payload(output_dir=mac_control_root)
        try:
            checkpoint_path, checkpoint = publish_maturity_checkpoint(
                feed=feed,
                qr_inventory=_read_object(artifact_root / "inventory.json"),
                mac_control_report=mac_control_report,
                mac_control_inventory=mac_control_inventory,
                mac_control_summary=mac_control_summary,
                mac_control_replay=mac_control_replay,
                fleet_root=publication_root,
            )
        except (MaturityCheckpointError, OSError, ValueError) as error:
            raise MaturityFeedError(
                f"coordinated maturity checkpoint was not published: {error}"
            ) from error
        feed_path = publication_root / "current" / "maturity.json"
    else:
        checkpoint_state = _read_object(artifact_root / "maturity-checkpoint.json")
        if not checkpoint_state:
            checkpoint_state = _read_object(artifact_root / "inventory.json").get(
                "maturity_checkpoint"
            )
        if isinstance(checkpoint_state, dict) and checkpoint_state.get("status") == "blocked":
            raise MaturityFeedError(
                "the QR audit's coordinated Mac Control lane is blocked; maturity feed was not published"
            )
        if isinstance(checkpoint_state, dict) and checkpoint_state.get("status") not in {
            None,
            "not_requested",
            "not_applicable",
        }:
            raise MaturityFeedError(
                "the QR audit's coordinated Mac Control artifacts are missing; maturity feed was not published"
            )
        feed_path = publish_maturity_feed(feed, publication_root)
    return {
        "schema": "quality-runner-maturity-feed-publication/v1",
        "status": "published",
        "audit_id": feed["source"]["audit_id"],
        "artifact_root": str(artifact_root),
        "feed_path": str(feed_path),
        "checkpoint_path": str(checkpoint_path) if checkpoint_path else None,
        "checkpoint": checkpoint,
        "provenance_hash": feed["provenance_hash"],
        "replay": replay,
        "feed": feed,
        "implementation_allowed": False,
    }


def _mac_control_artifact_root(artifact_root: Path) -> Path | None:
    nested_root = artifact_root / "mac-control"
    candidates = sorted(
        path.parent
        for path in nested_root.glob("*/inventory.json")
        if path.is_file() and not path.is_symlink()
    )
    if len(candidates) > 1:
        raise MaturityFeedError(
            "QR audit contains more than one nested Mac Control audit; publication is ambiguous"
        )
    return candidates[0] if candidates else None


def _read_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


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
