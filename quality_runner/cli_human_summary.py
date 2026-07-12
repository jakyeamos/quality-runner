from __future__ import annotations

from typing import Any

from quality_runner import __version__
from quality_runner.cli_fix_proposals import FIX_PROPOSAL_RESULT_SCHEMAS
from quality_runner.cli_gate import GATE_RESULT_SCHEMAS
from quality_runner.cli_status import EXPORT_HANDOFF_RESULT_SCHEMA, STATUS_RESULT_SCHEMA
from quality_runner.release_smoke import RELEASE_SMOKE_SCHEMA
from quality_runner.run_summary import RUN_SUMMARY_SCHEMA

DOCTOR_RESULT_SCHEMA = "quality-runner-doctor-result-v0.1"
INIT_RESULT_SCHEMA = "quality-runner-init-result-v0.1"


def human_summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "unknown")
    if payload.get("schema") == DOCTOR_RESULT_SCHEMA:
        version = payload.get("version", __version__)
        return f"Quality Runner {version}: {status}"
    if payload.get("schema") == INIT_RESULT_SCHEMA:
        return f"config: {payload.get('config_path')}"
    if payload.get("schema") == "quality-runner-review-result-v0.1":
        packet_ready = status == "review-not-run"
        lines = [
            "outcome: review packet ready" if packet_ready else f"status: {status}",
            f"summary: {payload.get('summary')}",
            f"mode: {payload.get('mode')} scope: {payload.get('scope')} breadth: {payload.get('breadth')}",
            f"adapter: {payload.get('adapter_status')}",
            f"severity counts: {payload.get('severity_counts')}",
            f"evidence limitations: {payload.get('evidence_unavailable')}",
        ]
        saved_path = payload.get("saved_path")
        if isinstance(saved_path, str):
            lines.append(f"saved: {saved_path}")
        artifact_paths = payload.get("artifact_paths")
        packet_path = (
            artifact_paths.get("review_agent_packet_md")
            if isinstance(artifact_paths, dict)
            else None
        )
        if packet_ready and isinstance(packet_path, str):
            lines.append(f"review packet: {packet_path}")
        next_action = payload.get("next_action")
        if isinstance(next_action, str) and next_action:
            lines.append(f"next action: {next_action}")
        return "\n".join(lines)
    if payload.get("schema") == RELEASE_SMOKE_SCHEMA:
        return _release_smoke_summary(payload, status)
    if payload.get("schema") == STATUS_RESULT_SCHEMA:
        latest = payload.get("latest_run")
        run_id = latest.get("run_id") if isinstance(latest, dict) else "none"
        return f"status: {status}\nlatest run: {run_id}"
    if payload.get("schema") == EXPORT_HANDOFF_RESULT_SCHEMA:
        output_path = payload.get("output_path")
        if isinstance(output_path, str):
            return f"handoff: {output_path}"
        return f"handoff: {payload.get('source_path')}"
    if payload.get("schema") == RUN_SUMMARY_SCHEMA:
        lifecycle = payload.get("lifecycle_status")
        lines = [f"status: {status}", f"run id: {payload.get('run_id')}"]
        if isinstance(lifecycle, str) and lifecycle:
            lines.append(f"lifecycle: {lifecycle}")
        return "\n".join(lines)
    if payload.get("schema") in GATE_RESULT_SCHEMAS:
        gate_run = payload.get("gate_run")
        gate_run_id = gate_run.get("gate_run_id") if isinstance(gate_run, dict) else None
        lifecycle = gate_run.get("lifecycle_status") if isinstance(gate_run, dict) else None
        lines = [f"status: {status}"]
        if isinstance(gate_run_id, str):
            lines.append(f"gate run: {gate_run_id}")
        if isinstance(lifecycle, str):
            lines.append(f"lifecycle: {lifecycle}")
        awaiting = gate_run.get("awaiting") if isinstance(gate_run, dict) else None
        if isinstance(awaiting, dict):
            kind = awaiting.get("kind")
            if isinstance(kind, str):
                lines.append(f"awaiting: {kind}")
        return "\n".join(lines)
    if payload.get("schema") in FIX_PROPOSAL_RESULT_SCHEMAS:
        lines = [f"status: {status}", f"finding group: {payload.get('finding_group')}"]
        proposal_count = payload.get("proposal_count")
        if isinstance(proposal_count, int):
            lines.append(f"proposals: {proposal_count}")
        proposal_id = payload.get("proposal_id")
        if isinstance(proposal_id, str):
            lines.append(f"proposal id: {proposal_id}")
        return "\n".join(lines)
    if payload.get("schema") == "quality-runner-refresh-result-v0.1":
        return _refresh_summary(payload, status)
    if payload.get("schema") == "quality-runner-rollout-result-v0.1":
        return _rollout_summary(payload, status)
    return _default_summary(payload, status)


def _release_smoke_summary(payload: dict[str, Any], status: object) -> str:
    handoff = payload.get("handoff_output")
    lines = [f"status: {status}"]
    if isinstance(handoff, str):
        lines.append(f"handoff: {handoff}")
    return "\n".join(lines)


def _refresh_summary(payload: dict[str, Any], status: object) -> str:
    summary = payload.get("summary")
    run_id = summary.get("run_id") if isinstance(summary, dict) else payload.get("run_id_prefix")
    lines = [f"status: {status}", f"run id: {run_id}"]
    handoff_export = payload.get("handoff_export")
    if isinstance(handoff_export, dict):
        output_path = handoff_export.get("output_path")
        if isinstance(output_path, str):
            lines.append(f"handoff: {output_path}")
    delta = payload.get("review_delta")
    if isinstance(delta, dict):
        lines.append(f"review cycle: {delta.get('cycle_id')} iteration {delta.get('iteration')}")
        lines.append(f"review recommendation: {'stop' if delta.get('clean') else 'continue'}")
        delta_paths = payload.get("review_delta_paths")
        if isinstance(delta_paths, dict) and isinstance(delta_paths.get("review_delta_md"), str):
            lines.append(f"review delta: {delta_paths['review_delta_md']}")
    return "\n".join(lines)


def _rollout_summary(payload: dict[str, Any], status: object) -> str:
    lines = [f"status: {status}"]
    ledger_path = payload.get("ledger_path")
    if isinstance(ledger_path, str):
        lines.append(f"ledger: {ledger_path}")
    repo_count = payload.get("repo_count")
    if isinstance(repo_count, int):
        lines.append(f"repos: {repo_count}")
    accepted = payload.get("accepted_reports")
    rejected = payload.get("rejected_reports")
    if isinstance(accepted, int) and isinstance(rejected, int):
        lines.append(f"controller reports: {accepted} accepted, {rejected} rejected")
    fleet_documents = payload.get("fleet_documents")
    if isinstance(fleet_documents, dict):
        index_md = fleet_documents.get("index_md")
        phase_md = fleet_documents.get("phase_md")
        if isinstance(index_md, str):
            lines.append(f"repo docs: {index_md}")
        if isinstance(phase_md, str):
            lines.append(f"phase draft: {phase_md}")
    return "\n".join(lines)


def _default_summary(payload: dict[str, Any], status: object) -> str:
    lines = [f"status: {status}"]
    run_id = payload.get("run_id")
    if isinstance(run_id, str):
        lines.append(f"run id: {run_id}")

    artifact_paths = payload.get("artifact_paths")
    if isinstance(artifact_paths, dict):
        _append_artifact_lines(lines, artifact_paths)
    return "\n".join(lines)


def _append_artifact_lines(lines: list[str], artifact_paths: dict[str, Any]) -> None:
    handoff_path = artifact_paths.get("agent_handoff_md")
    audit_path = artifact_paths.get("quality_audit_json")
    repo_scan_path = artifact_paths.get("repo_scan_json")
    if isinstance(handoff_path, str):
        lines.append(f"handoff: {handoff_path}")
    if isinstance(audit_path, str):
        lines.append(f"audit: {audit_path}")
    elif isinstance(repo_scan_path, str):
        lines.append(f"repo scan: {repo_scan_path}")
