from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from quality_runner.artifacts import artifact_dir, write_json
from quality_runner.gate_resolution_bridge import (
    apply_record_disposition,
    enrich_record_disposition_response,
    find_active_gate_run_id,
)
from quality_runner.intent import resolve_workflow_intent
from quality_runner.run_summary import build_run_summary
from quality_runner.schema_constants import GATE_RESPONSE_SCHEMA, GATE_RUN_SCHEMA

GATE_RUN_RESULT_SCHEMA = "quality-runner-gate-run-result-v0.1"
GATE_STATUS_RESULT_SCHEMA = "quality-runner-gate-status-result-v0.1"
GATE_RESPOND_RESULT_SCHEMA = "quality-runner-gate-respond-result-v0.1"

GATE_RUN_STATUSES = {"awaiting-response", "ready-to-proceed", "completed", "aborted"}
GATE_RESPONSE_ACTIONS = {
    "approve",
    "fix",
    "skip",
    "route-next-slice",
    "record-disposition",
    "abort",
}
TERMINAL_GATE_RUN_STATUSES = {"completed", "aborted"}


def generated_gate_run_id(now: datetime | None = None) -> str:
    timestamp = datetime.now(UTC) if now is None else now.astimezone(UTC)
    return f"gate-{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"


def gate_run_dir(repo_root: Path, gate_run_id: str) -> Path:
    _validate_gate_run_id(gate_run_id)
    return repo_root.expanduser().resolve() / ".quality-runner" / "gate-runs" / gate_run_id


def create_gate_run(
    *,
    repo_root: Path,
    run_id: str,
    gate_run_id: str | None = None,
    goal: str | None = None,
    intent_file: Path | None = None,
    actor: str = "user",
) -> dict[str, Any]:
    resolved_run_id = run_id.strip()
    resolved_gate_run_id = gate_run_id or generated_gate_run_id()
    run_dir = artifact_dir(repo_root, resolved_run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"run does not exist: {resolved_run_id}")

    handoff_path = run_dir / "agent-handoff.json"
    if not handoff_path.exists():
        raise FileNotFoundError(f"agent handoff does not exist for run: {resolved_run_id}")

    active_gate_run_id = find_active_gate_run_id(repo_root=repo_root, run_id=resolved_run_id)
    if active_gate_run_id is not None and active_gate_run_id != resolved_gate_run_id:
        raise ValueError(
            f"an active gate run already exists for run {resolved_run_id}: {active_gate_run_id}"
        )

    handoff = _load_json(handoff_path)
    summary = build_run_summary(
        repo_root=repo_root,
        run_id=resolved_run_id,
        persist=False,
    )
    lifecycle_status = _lifecycle_status(handoff, summary)
    handoff_status = handoff.get("status") if isinstance(handoff.get("status"), str) else None
    phase = "post-verify" if (run_dir / "gate-verification.json").exists() else "post-run"
    awaiting = _derive_awaiting(handoff=handoff, lifecycle_status=lifecycle_status)
    status = "ready-to-proceed" if awaiting is None else "awaiting-response"
    now = datetime.now(UTC).isoformat()

    gate_dir = _prepare_gate_run_dir(repo_root, resolved_gate_run_id)
    intent_ref = _attach_gate_intent(
        repo_root=repo_root,
        run_id=resolved_run_id,
        run_dir=run_dir,
        gate_dir=gate_dir,
        goal=goal,
        intent_file=intent_file,
        actor=actor,
    )
    artifact_paths = _artifact_paths(repo_root=repo_root, run_dir=run_dir, gate_dir=gate_dir)
    gate_run = {
        "schema": GATE_RUN_SCHEMA,
        "run_id": resolved_run_id,
        "gate_run_id": resolved_gate_run_id,
        "status": status,
        "phase": phase,
        "awaiting": awaiting,
        "lifecycle_status": lifecycle_status,
        "handoff_status": handoff_status,
        "artifact_paths": artifact_paths,
        "intent_ref": intent_ref,
        "implementation_allowed": False,
        "created_at": now,
        "updated_at": now,
        "last_response_at": None,
    }
    write_json(gate_dir / "gate-run.json", gate_run)
    return gate_run_payload(gate_run)


def gate_run_payload(gate_run: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": GATE_RUN_RESULT_SCHEMA,
        "status": gate_run.get("status"),
        "implementation_allowed": False,
        "gate_run": gate_run,
        "gate_run_path": _gate_run_path(gate_run),
    }


def gate_status_payload(*, repo_root: Path, gate_run_id: str) -> dict[str, Any]:
    gate_run = load_gate_run(repo_root=repo_root, gate_run_id=gate_run_id)
    responses = load_gate_responses(repo_root=repo_root, gate_run_id=gate_run_id)
    return {
        "schema": GATE_STATUS_RESULT_SCHEMA,
        "status": gate_run.get("status"),
        "implementation_allowed": False,
        "gate_run": gate_run,
        "responses": responses,
        "gate_run_path": _gate_run_path(gate_run),
        "responses_path": _responses_path(repo_root, gate_run_id),
    }


def record_gate_response(
    *,
    repo_root: Path,
    gate_run_id: str,
    action: str,
    actor: str = "user",
    finding_ids: list[str] | None = None,
    notes: str | None = None,
    disposition: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    if action not in GATE_RESPONSE_ACTIONS:
        raise ValueError(f"unsupported gate response action: {action}")

    gate_run = load_gate_run(repo_root=repo_root, gate_run_id=gate_run_id)
    current_status = gate_run.get("status")
    if current_status in TERMINAL_GATE_RUN_STATUSES:
        raise ValueError(f"gate run is already terminal: {current_status}")

    now = datetime.now(UTC).isoformat()
    response = {
        "schema": GATE_RESPONSE_SCHEMA,
        "gate_run_id": gate_run_id,
        "run_id": gate_run.get("run_id"),
        "at": now,
        "actor": actor,
        "action": action,
        "finding_ids": finding_ids or [],
        "notes": notes,
    }
    if action == "record-disposition":
        run_id = gate_run.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("gate run is missing run_id for record-disposition")
        response = enrich_record_disposition_response(
            repo_root=repo_root,
            run_id=run_id,
            response=response,
            disposition=disposition or "accepted-intentional",
            owner=owner or actor,
        )
    responses_path = _append_gate_response(
        repo_root=repo_root, gate_run_id=gate_run_id, response=response
    )
    if action == "record-disposition" and isinstance(gate_run.get("run_id"), str):
        apply_record_disposition(
            repo_root=repo_root,
            run_id=gate_run["run_id"],
            gate_run_id=gate_run_id,
            response=response,
        )

    updated_status = _status_after_response(current_status=current_status, action=action)
    gate_run["status"] = updated_status
    gate_run["updated_at"] = now
    gate_run["last_response_at"] = now
    if updated_status == "ready-to-proceed":
        gate_run["awaiting"] = None

    gate_dir = gate_run_dir(repo_root, gate_run_id)
    write_json(gate_dir / "gate-run.json", gate_run)

    return {
        "schema": GATE_RESPOND_RESULT_SCHEMA,
        "status": updated_status,
        "implementation_allowed": False,
        "gate_run": gate_run,
        "response": response,
        "responses_path": str(responses_path),
    }


def load_gate_run(*, repo_root: Path, gate_run_id: str) -> dict[str, Any]:
    path = gate_run_dir(repo_root, gate_run_id) / "gate-run.json"
    if not path.exists():
        raise FileNotFoundError(f"gate run does not exist: {gate_run_id}")
    payload = _load_json(path)
    if payload.get("schema") != GATE_RUN_SCHEMA:
        raise ValueError("gate-run.json schema mismatch")
    return payload


def load_gate_responses(*, repo_root: Path, gate_run_id: str) -> list[dict[str, Any]]:
    path = Path(_responses_path(repo_root, gate_run_id))
    if not path.exists():
        return []
    responses: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            responses.append(payload)
    return responses


def _status_after_response(*, current_status: object, action: str) -> str:
    if action == "abort":
        return "aborted"
    if action == "approve":
        return "completed"
    if action == "skip" and current_status == "ready-to-proceed":
        return "completed"
    return "awaiting-response" if current_status != "ready-to-proceed" else "ready-to-proceed"


def _derive_awaiting(*, handoff: dict[str, Any], lifecycle_status: str) -> dict[str, Any] | None:
    if lifecycle_status in {"merge-ready", "audit-clean"}:
        return None

    since = datetime.now(UTC).isoformat()
    gate_verification = handoff.get("gate_verification")
    if isinstance(gate_verification, dict):
        primary_blocker_class = gate_verification.get("primary_blocker_class")
        if handoff.get("status") in {"gates-blocked", "gates-failed"}:
            return {
                "kind": "blocker-routing",
                "primary_blocker_class": (
                    primary_blocker_class if isinstance(primary_blocker_class, str) else None
                ),
                "since": since,
            }

    if lifecycle_status == "workflow-timeout":
        return {"kind": "workflow-timeout", "primary_blocker_class": None, "since": since}

    next_slice = handoff.get("next_slice")
    if isinstance(next_slice, dict):
        findings = next_slice.get("findings")
        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                if finding.get("actionability") == "needs-author-decision":
                    return {
                        "kind": "author-decision",
                        "primary_blocker_class": None,
                        "since": since,
                    }
            if findings:
                return {
                    "kind": "finding-triage",
                    "primary_blocker_class": None,
                    "since": since,
                }

    if lifecycle_status in {"blocked", "failed", "needs-triage"}:
        return {"kind": "finding-triage", "primary_blocker_class": None, "since": since}

    if lifecycle_status == "gates-clean":
        return None

    return None


def _lifecycle_status(handoff: dict[str, Any], summary: dict[str, Any]) -> str:
    lifecycle_status = handoff.get("lifecycle_status")
    if isinstance(lifecycle_status, str) and lifecycle_status:
        return lifecycle_status
    summary_lifecycle = summary.get("lifecycle_status")
    if isinstance(summary_lifecycle, str) and summary_lifecycle:
        return summary_lifecycle
    return "needs-triage"


def _artifact_paths(*, repo_root: Path, run_dir: Path, gate_dir: Path) -> dict[str, str]:
    repo = repo_root.expanduser().resolve()

    def relative(path: Path) -> str:
        return path.resolve().relative_to(repo).as_posix()

    paths = {
        "gate_run_json": relative(gate_dir / "gate-run.json"),
        "gate_responses_jsonl": relative(gate_dir / "gate-responses.jsonl"),
        "agent_handoff_json": relative(run_dir / "agent-handoff.json"),
        "agent_handoff_md": relative(run_dir / "agent-handoff.md"),
        "quality_audit_json": relative(run_dir / "quality-audit.json"),
        "run_manifest_json": relative(run_dir / "run-manifest.json"),
    }
    gate_verification = run_dir / "gate-verification.json"
    if gate_verification.exists():
        paths["gate_verification_json"] = relative(gate_verification)
    run_summary = run_dir / "run-summary.json"
    if run_summary.exists():
        paths["run_summary_json"] = relative(run_summary)
    intent_path = run_dir / "intent.json"
    if intent_path.exists():
        paths["intent_json"] = relative(intent_path)
    resolution_ledger = run_dir / "resolution-ledger.json"
    if resolution_ledger.exists():
        paths["resolution_ledger_json"] = relative(resolution_ledger)
    return paths


def _attach_gate_intent(
    *,
    repo_root: Path,
    run_id: str,
    run_dir: Path,
    gate_dir: Path,
    goal: str | None,
    intent_file: Path | None,
    actor: str,
) -> str | None:
    run_intent_path = run_dir / "intent.json"
    if run_intent_path.exists():
        return run_intent_path.resolve().relative_to(repo_root.resolve()).as_posix()

    intent = resolve_workflow_intent(
        repo_root=repo_root,
        run_id=run_id,
        goal=goal,
        intent_file=intent_file,
        source="gate",
        supplied_by=actor,
    )
    if intent is None:
        return None

    intent_path = gate_dir / "intent.json"
    write_json(intent_path, intent)
    return intent_path.resolve().relative_to(repo_root.resolve()).as_posix()


def _append_gate_response(
    *,
    repo_root: Path,
    gate_run_id: str,
    response: dict[str, Any],
) -> Path:
    gate_dir = _prepare_gate_run_dir(repo_root, gate_run_id)
    path = gate_dir / "gate-responses.jsonl"
    if path.is_symlink():
        raise ValueError("gate response log must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(response, sort_keys=True) + "\n")
    return path


def _prepare_gate_run_dir(repo_root: Path, gate_run_id: str) -> Path:
    _validate_gate_run_id(gate_run_id)
    root = repo_root.expanduser().resolve()
    current = root
    for segment in (".quality-runner", "gate-runs", gate_run_id):
        current = current / segment
        if current.is_symlink():
            raise ValueError("gate run path component must not be a symlink")
        if current.exists() and not current.is_dir():
            raise ValueError("gate run path component must be a directory")
        if not current.exists():
            current.mkdir()
    return current


def _responses_path(repo_root: Path, gate_run_id: str) -> str:
    return str(gate_run_dir(repo_root, gate_run_id) / "gate-responses.jsonl")


def _gate_run_path(gate_run: dict[str, Any]) -> str | None:
    artifact_paths = gate_run.get("artifact_paths")
    if isinstance(artifact_paths, dict):
        path = artifact_paths.get("gate_run_json")
        if isinstance(path, str) and path:
            return path
    return None


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _validate_gate_run_id(gate_run_id: str) -> None:
    path = Path(gate_run_id)
    separators = {"/", "\\"}
    if (
        not gate_run_id
        or gate_run_id in {".", ".."}
        or ":" in gate_run_id
        or path.is_absolute()
        or any(separator in gate_run_id for separator in separators)
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise ValueError("gate_run_id must be a non-empty single path segment")
