from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.audit import build_audit_report
from quality_runner.capabilities import detect_capabilities
from quality_runner.discovery import inspect_repo
from quality_runner.findings import (
    validate_agent_handoff,
    validate_audit_report,
    validate_remediation_plan,
)
from quality_runner.planning import (
    build_agent_handoff,
    build_remediation_plan,
    render_handoff_markdown,
)
from quality_runner.standards import compile_standards


def generated_run_id(now: datetime | None = None, suffix: str | None = None) -> str:
    timestamp = datetime.now(UTC) if now is None else now.astimezone(UTC)
    run_suffix = uuid4().hex[:8] if suffix is None else suffix
    return f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{run_suffix}"


def inspect_payload(
    repo_root: Path, run_id: str | None = None, profile: str = "jakyeamos"
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    scan, standards_packet, capability_map = _inspect(repo_root, resolved_run_id, profile)

    artifact_paths = {
        "repo_scan_json": str(write_json(run_dir / "repo-scan.json", scan)),
        "standards_json": str(write_json(run_dir / "standards.json", standards_packet)),
        "capability_matrix_json": str(
            write_json(run_dir / "capability-matrix.json", capability_map)
        ),
    }

    return {
        "schema": "quality-runner-inspect-result-v0.1",
        "status": "inspected",
        "implementation_allowed": False,
        "run_id": resolved_run_id,
        "artifact_paths": artifact_paths,
        "warnings": capability_map["warnings"],
    }


def run_payload(
    repo_root: Path, run_id: str | None = None, profile: str = "jakyeamos"
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    scan, standards_packet, capability_map = _inspect(repo_root, resolved_run_id, profile)

    audit_report = build_audit_report(
        scan=scan,
        standards_packet=standards_packet,
        capability_map=capability_map,
    )
    _require_valid("audit report", validate_audit_report(audit_report))

    remediation_plan = build_remediation_plan(
        audit_report=audit_report,
        capability_map=capability_map,
    )
    _require_valid("remediation plan", validate_remediation_plan(remediation_plan))
    status = "clean" if not remediation_plan["slices"] else "planned"

    artifact_paths = {
        "repo_scan_json": str(run_dir / "repo-scan.json"),
        "standards_json": str(run_dir / "standards.json"),
        "capability_matrix_json": str(run_dir / "capability-matrix.json"),
        "quality_audit_json": str(run_dir / "quality-audit.json"),
        "remediation_plan_json": str(run_dir / "remediation-plan.json"),
        "agent_handoff_json": str(run_dir / "agent-handoff.json"),
        "agent_handoff_md": str(run_dir / "agent-handoff.md"),
    }
    handoff = build_agent_handoff(
        audit_report=audit_report,
        remediation_plan=remediation_plan,
        artifact_paths=artifact_paths,
    )
    _require_valid("agent handoff", validate_agent_handoff(handoff))

    artifact_paths["repo_scan_json"] = str(write_json(run_dir / "repo-scan.json", scan))
    artifact_paths["standards_json"] = str(write_json(run_dir / "standards.json", standards_packet))
    artifact_paths["capability_matrix_json"] = str(
        write_json(run_dir / "capability-matrix.json", capability_map)
    )
    artifact_paths["quality_audit_json"] = str(
        write_json(run_dir / "quality-audit.json", audit_report)
    )
    artifact_paths["remediation_plan_json"] = str(
        write_json(run_dir / "remediation-plan.json", remediation_plan)
    )
    artifact_paths["agent_handoff_json"] = str(write_json(run_dir / "agent-handoff.json", handoff))
    artifact_paths["agent_handoff_md"] = str(
        write_text(run_dir / "agent-handoff.md", render_handoff_markdown(handoff))
    )

    return {
        "schema": "quality-runner-run-result-v0.1",
        "status": status,
        "implementation_allowed": False,
        "run_id": resolved_run_id,
        "artifact_paths": artifact_paths,
        "warnings": capability_map["warnings"],
    }


def _inspect(
    repo_root: Path,
    run_id: str,
    profile: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    scan = inspect_repo(repo_root, run_id=run_id)
    standards_packet = compile_standards(repo_root=repo_root, scan=scan, profile=profile)
    capability_map = detect_capabilities(scan=scan, standards_packet=standards_packet)
    return scan, standards_packet, capability_map


def _require_valid(name: str, result: dict[str, Any]) -> None:
    if result.get("passed") is True:
        return
    errors = result.get("errors")
    if isinstance(errors, list) and errors:
        message = "; ".join(str(error) for error in errors)
    else:
        message = "unknown validation error"
    raise ValueError(f"invalid {name}: {message}")
