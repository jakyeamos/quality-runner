from __future__ import annotations

from typing import Any

from quality_runner import __version__
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
        return f"status: {status}\nrun id: {payload.get('run_id')}"
    if payload.get("schema") == "quality-runner-refresh-result-v0.1":
        return _refresh_summary(payload, status)
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
