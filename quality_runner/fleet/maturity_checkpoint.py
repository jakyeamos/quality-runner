from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quality_runner.artifacts import prepare_safe_directory, write_json
from quality_runner.fleet.contracts import digest, stable_id
from quality_runner.fleet.maturity_feed import validate_maturity_feed

MATURITY_CHECKPOINT_SCHEMA = "quality-runner-maturity-checkpoint/v1"
MATURITY_CHECKPOINT_RELATIVE_PATH = Path("current") / "maturity-checkpoint.json"
MATURITY_CHECKPOINT_BUNDLE_RELATIVE_PATH = Path("current") / "checkpoints"
MATURITY_CHECKPOINT_MAX_AGE_DAYS = 7


class MaturityCheckpointError(ValueError):
    """Raised when two fleet evidence lanes cannot form one checkpoint."""


def build_maturity_checkpoint(
    *,
    feed: Mapping[str, Any],
    qr_inventory: Mapping[str, Any],
    mac_control_report: Mapping[str, Any],
    mac_control_inventory: Mapping[str, Any],
    mac_control_summary: Mapping[str, Any],
    mac_control_replay: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the pointer payload that binds the QR and Mac Control lanes."""

    validate_maturity_feed(dict(feed))
    qr_audit_id = _required_string(_object(feed.get("source")), "audit_id")
    qr_as_of = _required_string(_object(feed.get("source")), "as_of")
    if _required_string(qr_inventory, "audit_id") != qr_audit_id:
        raise MaturityCheckpointError("QR inventory and maturity feed audit IDs do not match")
    if _required_string(qr_inventory, "as_of") != qr_as_of:
        raise MaturityCheckpointError("QR inventory and maturity feed observations do not match")

    if (
        mac_control_replay.get("status") != "passed"
        or mac_control_replay.get("deterministic") is not True
    ):
        raise MaturityCheckpointError("Mac Control replay must pass before checkpoint publication")
    mac_control_audit_id = _required_string(mac_control_inventory, "audit_id")
    if mac_control_replay.get("audit_id") != mac_control_audit_id:
        raise MaturityCheckpointError("Mac Control replay and inventory audit IDs do not match")
    mac_control_as_of = _required_string(mac_control_inventory, "as_of")
    if mac_control_as_of != qr_as_of:
        raise MaturityCheckpointError(
            "QR and Mac Control observations must use the same as_of timestamp"
        )
    if _required_string(mac_control_report, "run_id") != mac_control_audit_id:
        raise MaturityCheckpointError("Mac Control report and inventory audit IDs do not match")
    if _required_string(mac_control_report, "observed_at") != qr_as_of:
        raise MaturityCheckpointError(
            "QR and Mac Control reports must use the same observed_at timestamp"
        )

    qr_commits = _qr_primary_commits(qr_inventory)
    mac_control_commits = _mac_control_commits(mac_control_inventory)
    if set(qr_commits) != set(mac_control_commits):
        raise MaturityCheckpointError("QR and Mac Control repository populations do not match")
    mismatched = sorted(
        repository_id
        for repository_id, commit in qr_commits.items()
        if not commit or mac_control_commits.get(repository_id) != commit
    )
    if mismatched:
        raise MaturityCheckpointError(
            "QR and Mac Control observed commits do not match for: " + ", ".join(mismatched)
        )

    feed_repository_ids = {
        _required_string(repository, "repo_id") for repository in _objects(feed.get("repositories"))
    }
    if feed_repository_ids != set(qr_commits):
        raise MaturityCheckpointError(
            "QR maturity projections and inventory repository populations do not match"
        )

    checkpoint_id = stable_id(
        "maturity-checkpoint",
        qr_audit_id,
        mac_control_audit_id,
        qr_as_of,
        sorted(qr_commits.items()),
    )
    repositories = [
        {"repo_id": repository_id, "observed_commit": qr_commits[repository_id]}
        for repository_id in sorted(qr_commits)
    ]
    # A coherent checkpoint can contain failed or review-required evidence. The
    # quality result is deliberately separate from the publication/coherence
    # result so freshness is never mistaken for passing behavior.
    quality_status = (
        "ready_with_blockers"
        if feed.get("status") == "complete_with_blockers"
        or mac_control_summary.get("status") not in {None, "passed"}
        else "ready"
    )
    bundle = MATURITY_CHECKPOINT_BUNDLE_RELATIVE_PATH / checkpoint_id
    return {
        "schema": MATURITY_CHECKPOINT_SCHEMA,
        "status": "complete",
        "publication_status": "ready",
        "quality_status": quality_status,
        "checkpoint_id": checkpoint_id,
        "observed_at": qr_as_of,
        "freshness_policy": {
            "max_age_days": MATURITY_CHECKPOINT_MAX_AGE_DAYS,
            "evaluation": "consumer_evaluated",
        },
        "target": {
            "projects_root": _required_string(_object(feed.get("source")), "projects_root"),
            "repository_count": len(repositories),
            "repositories": repositories,
        },
        "components": {
            "qr_maturity": {
                "schema": feed.get("schema"),
                "audit_id": qr_audit_id,
                "as_of": qr_as_of,
                "path": str(bundle / "maturity.json"),
            },
            "mac_control": {
                "schema": mac_control_report.get("schema_version"),
                "audit_id": mac_control_audit_id,
                "as_of": qr_as_of,
                "path": str(bundle / "mac-control-ideal-state.json"),
            },
        },
        "provenance": {
            "qr_feed_hash": digest(feed),
            "mac_control_report_hash": digest(mac_control_report),
            "mac_control_replay_hash": digest(mac_control_replay),
        },
    }


def publish_maturity_checkpoint(
    *,
    feed: Mapping[str, Any],
    qr_inventory: Mapping[str, Any],
    mac_control_report: Mapping[str, Any],
    mac_control_inventory: Mapping[str, Any],
    mac_control_summary: Mapping[str, Any],
    mac_control_replay: Mapping[str, Any],
    fleet_root: Path,
) -> tuple[Path, dict[str, Any]]:
    """Write the versioned bundle and atomically replace its stable pointer."""

    checkpoint = build_maturity_checkpoint(
        feed=feed,
        qr_inventory=qr_inventory,
        mac_control_report=mac_control_report,
        mac_control_inventory=mac_control_inventory,
        mac_control_summary=mac_control_summary,
        mac_control_replay=mac_control_replay,
    )
    root = fleet_root.expanduser()
    current = root / "current"
    prepare_safe_directory(current)
    bundle_relative = MATURITY_CHECKPOINT_BUNDLE_RELATIVE_PATH / str(checkpoint["checkpoint_id"])
    bundle = root / bundle_relative
    prepare_safe_directory(bundle)

    qr_path = write_json(bundle / "maturity.json", dict(feed))
    mac_control_path = write_json(bundle / "mac-control-ideal-state.json", dict(mac_control_report))
    mac_control_summary_path = write_json(
        bundle / "mac-control-summary.json", dict(mac_control_summary)
    )
    checkpoint["components"]["qr_maturity"]["sha256"] = _file_sha256(qr_path)
    checkpoint["components"]["mac_control"]["sha256"] = _file_sha256(mac_control_path)
    checkpoint["supporting_artifacts"] = {
        "mac_control_summary": {
            "path": str(
                MATURITY_CHECKPOINT_BUNDLE_RELATIVE_PATH
                / str(checkpoint["checkpoint_id"])
                / "mac-control-summary.json"
            ),
            "sha256": _file_sha256(mac_control_summary_path),
        }
    }
    checkpoint["pointer_hash"] = digest(checkpoint)

    # Keep the two existing stable files updated for older consumers. New
    # consumers use the pointer and refuse to silently combine these sidecars.
    write_json(current / "maturity.json", dict(feed))
    write_json(current / "mac-control-ideal-state.json", dict(mac_control_report))
    write_json(current / "mac-control-summary.json", dict(mac_control_summary))
    pointer = root / str(MATURITY_CHECKPOINT_RELATIVE_PATH)
    _atomic_json_write(pointer, checkpoint)
    return pointer, checkpoint


def _qr_primary_commits(inventory: Mapping[str, Any]) -> dict[str, str]:
    return {
        repository_id: _primary_commit(repository)
        for repository in _objects(inventory.get("repositories"))
        if (repository_id := _required_string(repository, "repo_id"))
    }


def _primary_commit(repository: Mapping[str, Any]) -> str:
    checkouts = _objects(repository.get("checkouts"))
    primary = next((checkout for checkout in checkouts if checkout.get("is_primary") is True), None)
    candidate = primary or (checkouts[0] if checkouts else {})
    return str(candidate.get("head", ""))


def _mac_control_commits(inventory: Mapping[str, Any]) -> dict[str, str]:
    return {
        _required_string(repository, "repo_id"): str(repository.get("observed_commit", ""))
        for repository in _objects(inventory.get("repositories"))
    }


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    if path.is_symlink():
        raise MaturityCheckpointError(f"checkpoint pointer must not be a symlink: {path}")
    parent = path.parent
    prepare_safe_directory(parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-", suffix=".tmp", dir=str(parent)
    )
    temporary = Path(temporary_name)
    try:
        content = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required_string(value: Mapping[str, Any], key: str) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or not candidate.strip():
        raise MaturityCheckpointError(f"checkpoint field is missing: {key}")
    return candidate


def _object(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _objects(value: object) -> list[dict[str, Any]]:
    return (
        [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    )
