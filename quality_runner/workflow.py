from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.audit import build_audit_report
from quality_runner.capabilities import detect_capabilities
from quality_runner.ci_status import load_ci_status
from quality_runner.config import load_repo_config
from quality_runner.discovery import inspect_repo
from quality_runner.findings import (
    validate_agent_handoff,
    validate_audit_report,
    validate_remediation_plan,
)
from quality_runner.manifest import build_run_manifest
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
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    scan, standards_packet, capability_map = _inspect(
        repo_root, resolved_run_id, profile, ci_status_json
    )

    artifact_paths = {
        "repo_scan_json": str(write_json(run_dir / "repo-scan.json", scan)),
        "standards_json": str(write_json(run_dir / "standards.json", standards_packet)),
        "capability_matrix_json": str(
            write_json(run_dir / "capability-matrix.json", capability_map)
        ),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
    }
    inspect_manifest = build_run_manifest(
        repo_root=repo_root,
        run_id=resolved_run_id,
        mode="inspect",
        artifact_paths=artifact_paths,
    )
    artifact_paths["run_manifest_json"] = str(
        write_json(run_dir / "run-manifest.json", inspect_manifest)
    )

    return {
        "schema": "quality-runner-inspect-result-v0.1",
        "status": "inspected",
        "implementation_allowed": False,
        "run_id": resolved_run_id,
        "artifact_paths": artifact_paths,
        "warnings": capability_map["warnings"],
    }


def run_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    scan, standards_packet, capability_map = _inspect(
        repo_root, resolved_run_id, profile, ci_status_json
    )

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
        "run_manifest_json": str(run_dir / "run-manifest.json"),
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
    run_manifest = build_run_manifest(
        repo_root=repo_root,
        run_id=resolved_run_id,
        mode="run",
        artifact_paths=artifact_paths,
    )
    artifact_paths["run_manifest_json"] = str(
        write_json(run_dir / "run-manifest.json", run_manifest)
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
    repo_root: Path, run_id: str, profile: str | None, ci_status_json: Path | None
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ci_checks, ci_warnings = load_ci_status(repo_root, ci_status_json)
    config = load_repo_config(repo_root)
    scan = inspect_repo(
        repo_root,
        run_id=run_id,
        ci_checks=ci_checks,
        extra_warnings=ci_warnings,
        config=config,
    )
    resolved_profile = profile or _string_or_default(config.get("default_profile"), "jakyeamos")
    standards_packet = compile_standards(
        repo_root=repo_root, scan=scan, profile=resolved_profile, config=config
    )
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


def _string_or_default(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default
