from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from quality_runner import __version__
from quality_runner.artifacts import prepare_directory, safe_child_file, write_json

GATE_RECEIPT_SCHEMA = "quality-runner-task-gate-receipt/v1"


def cached_gate_result(
    *,
    repo_root: Path,
    snapshot_digest: str | None,
    gate: dict[str, Any],
    bootstrap: dict[str, Any],
) -> dict[str, Any] | None:
    key = _gate_receipt_key(
        snapshot_digest=snapshot_digest,
        gate=gate,
        bootstrap=bootstrap,
    )
    if key is None:
        return None
    path = repo_root / ".quality-runner" / "cache" / "gate-receipts-v1" / f"{key}.json"
    if not path.is_file():
        return None
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(receipt, dict):
        return None
    result = receipt.get("result")
    if not (
        receipt.get("schema") == GATE_RECEIPT_SCHEMA
        and receipt.get("receipt_key") == key
        and isinstance(result, dict)
        and result.get("status") == "passed"
        and result.get("id") == gate.get("id")
    ):
        return None
    cached = cast(dict[str, Any], dict(result))
    cached["bootstrap"] = bootstrap
    cached["duration_seconds"] = 0.0
    cached["receipt_reuse"] = {
        "status": "hit",
        "receipt_key": key,
        "source_duration_seconds": result.get("duration_seconds"),
    }
    return cached


def store_gate_result(
    *,
    repo_root: Path,
    snapshot_digest: str | None,
    gate: dict[str, Any],
    bootstrap: dict[str, Any],
    result: dict[str, Any],
) -> None:
    key = _gate_receipt_key(
        snapshot_digest=snapshot_digest,
        gate=gate,
        bootstrap=bootstrap,
    )
    if key is None:
        return
    try:
        directory = prepare_directory(repo_root, ".quality-runner", "cache", "gate-receipts-v1")
        write_json(
            safe_child_file(directory, f"{key}.json"),
            {
                "schema": GATE_RECEIPT_SCHEMA,
                "receipt_key": key,
                "snapshot_digest": snapshot_digest,
                "result": result,
            },
        )
    except (OSError, ValueError):
        # Receipt persistence is an optimization. A passing live gate remains
        # authoritative when the local cache is unavailable.
        return


def _gate_receipt_key(
    *,
    snapshot_digest: str | None,
    gate: dict[str, Any],
    bootstrap: dict[str, Any],
) -> str | None:
    if not snapshot_digest:
        return None
    payload = {
        "quality_runner_version": __version__,
        "snapshot_digest": snapshot_digest,
        "gate": {
            "id": gate.get("id"),
            "required": gate.get("required") is True,
            "command": gate.get("command"),
            "command_version": gate.get("command_version"),
            "timeout_seconds": gate.get("timeout_seconds"),
            "mutation_risk": gate.get("mutation_risk"),
            "scope": gate.get("scope"),
        },
        "bootstrap": {
            "command": bootstrap.get("command"),
            "command_version": bootstrap.get("command_version"),
            "status": bootstrap.get("status"),
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
