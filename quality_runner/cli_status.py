from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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

    handoff_path = repo_root / ".quality-runner" / "runs" / resolved_run_id / "agent-handoff.md"
    if not handoff_path.exists():
        raise FileNotFoundError(f"agent handoff does not exist for run: {resolved_run_id}")
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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        payload["output_path"] = str(output_path)
    return payload


def _latest_run(repo_root: Path) -> dict[str, Any] | None:
    run_id = _latest_run_id(repo_root)
    if run_id is None:
        return None
    run_dir = repo_root / ".quality-runner" / "runs" / run_id
    gate_verification_status = _gate_verification_status(run_dir)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "path": str(run_dir),
        "has_handoff": (run_dir / "agent-handoff.md").exists(),
        "has_audit": (run_dir / "quality-audit.json").exists(),
        "has_gate_verification": gate_verification_status is not None,
        "gate_verification_status": gate_verification_status,
    }
    module_status = _module_status(run_dir)
    if module_status is not None:
        payload["module_status"] = module_status
    return payload


def _repo_status(latest_run: dict[str, Any] | None) -> str:
    if latest_run is None:
        return "initialized"
    gate_status = latest_run.get("gate_verification_status")
    if gate_status in {"failed", "blocked"}:
        return "blocked"
    return "ready"


def _gate_verification_status(run_dir: Path) -> str | None:
    path = run_dir / "gate-verification.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "blocked"
    status = payload.get("status")
    return status if isinstance(status, str) and status else "blocked"


def _module_status(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / "repo-scan.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    status = payload.get("module_status")
    return status if isinstance(status, dict) else None


def _latest_run_id(repo_root: Path) -> str | None:
    runs_dir = repo_root / ".quality-runner" / "runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        return None
    candidates = [path for path in runs_dir.iterdir() if path.is_dir()]
    if not candidates:
        return None
    latest = max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))
    return latest.name
