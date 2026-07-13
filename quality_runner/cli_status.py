from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quality_runner.artifacts import (
    artifact_run_ids,
    artifact_text_file,
    existing_artifact_dir,
    safe_child_file,
    write_text,
)
from quality_runner.config import load_repo_config

EXPORT_HANDOFF_RESULT_SCHEMA = "quality-runner-export-handoff-result-v0.1"
STATUS_RESULT_SCHEMA = "quality-runner-status-result-v0.1"


def status_payload(repo_root: Path) -> dict[str, Any]:
    latest_run = _latest_run(repo_root)
    status = _repo_status(latest_run)
    return {
        "schema": STATUS_RESULT_SCHEMA,
        "status": status,
        "repo_root": str(repo_root),
        "implementation_allowed": False,
        "config": load_repo_config(repo_root),
        "latest_run": latest_run,
    }


def export_handoff_payload(
    *,
    repo_root: Path,
    run_id: str | None,
    output_path: Path | None,
) -> dict[str, Any]:
    resolved_run_id = _latest_run_id(repo_root) if run_id is None else run_id
    if resolved_run_id is None:
        raise FileNotFoundError("no Quality Runner runs found")

    handoff_path = artifact_text_file(repo_root, resolved_run_id, "agent-handoff.md")
    content = handoff_path.read_text(encoding="utf-8")

    payload = {
        "schema": EXPORT_HANDOFF_RESULT_SCHEMA,
        "status": "exported",
        "run_id": resolved_run_id,
        "source_path": str(handoff_path),
        "implementation_allowed": False,
    }
    if output_path is None:
        payload["content"] = content
    else:
        write_text(output_path, content)
        payload["output_path"] = str(output_path)
    return payload


def _latest_run(repo_root: Path) -> dict[str, Any] | None:
    run_id = _latest_run_id(repo_root)
    if run_id is None:
        return None
    run_dir = existing_artifact_dir(repo_root, run_id)
    gate_verification_status = _gate_verification_status(repo_root, run_id)
    return {
        "run_id": run_id,
        "path": str(run_dir),
        "has_handoff": _artifact_file_exists(run_dir, "agent-handoff.md"),
        "has_audit": _artifact_file_exists(run_dir, "quality-audit.json"),
        "has_gate_verification": gate_verification_status is not None,
        "gate_verification_status": gate_verification_status,
    }


def _repo_status(latest_run: dict[str, Any] | None) -> str:
    if latest_run is None:
        return "initialized"
    gate_status = latest_run.get("gate_verification_status")
    if gate_status in {"failed", "blocked"}:
        return "blocked"
    return "ready"


def _gate_verification_status(repo_root: Path, run_id: str) -> str | None:
    try:
        path = artifact_text_file(repo_root, run_id, "gate-verification.json")
    except FileNotFoundError:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "blocked"
    status = payload.get("status")
    return status if isinstance(status, str) and status else "blocked"


def _artifact_file_exists(run_dir: Path, filename: str) -> bool:
    try:
        safe_child_file(run_dir, filename, require_exists=True)
    except (FileNotFoundError, ValueError):
        return False
    return True


def _latest_run_id(repo_root: Path) -> str | None:
    run_ids = artifact_run_ids(repo_root)
    if not run_ids:
        return None
    runs_dir = existing_artifact_dir(repo_root, run_ids[0]).parent
    candidates = [runs_dir / run_id for run_id in run_ids]
    if not candidates:
        return None
    latest = max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))
    return latest.name
