from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.audit import build_audit_report
from quality_runner.capabilities import detect_capabilities
from quality_runner.ci_status import load_ci_status
from quality_runner.code_quality import (
    build_resolution_ledger,
    create_code_quality_scan,
    render_resolution_ledger_markdown,
)
from quality_runner.config import load_repo_config
from quality_runner.discovery import inspect_repo
from quality_runner.findings import (
    validate_agent_handoff,
    validate_audit_report,
    validate_remediation_plan,
)
from quality_runner.gate_verification import apply_gate_verification, verify_discovered_gates
from quality_runner.git_branches import prepare_scan_branch
from quality_runner.manifest import build_run_manifest
from quality_runner.package_preflight import build_package_manager_preflight
from quality_runner.planning import (
    build_agent_handoff,
    build_remediation_plan,
    render_handoff_markdown,
)
from quality_runner.standards import DEFAULT_PROFILE, compile_standards


def generated_run_id(now: datetime | None = None, suffix: str | None = None) -> str:
    timestamp = datetime.now(UTC) if now is None else now.astimezone(UTC)
    run_suffix = uuid4().hex[:8] if suffix is None else suffix
    return f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}-{run_suffix}"


def inspect_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    include_ignored_paths: list[str] | None = None,
    checkout_most_advanced_branch: bool = False,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    scan, standards_packet, capability_map, config = _inspect(
        repo_root, resolved_run_id, profile, ci_status_json, branch_warnings
    )
    config = _config_with_include_overrides(config, include_ignored_paths)
    code_quality_scan = create_code_quality_scan(repo_root, scan=scan, config=config)
    package_manager_preflight = build_package_manager_preflight(repo_root, scan)

    artifact_paths = {
        "repo_scan_json": str(write_json(run_dir / "repo-scan.json", scan)),
        "code_quality_scan_json": str(
            write_json(run_dir / "code-quality-scan.json", code_quality_scan)
        ),
        "package_manager_preflight_json": str(
            write_json(run_dir / "package-manager-preflight.json", package_manager_preflight)
        ),
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
        "warnings": _combined_warnings(scan, capability_map),
    }


def run_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    include_ignored_paths: list[str] | None = None,
    checkout_most_advanced_branch: bool = False,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    scan, standards_packet, capability_map, config = _inspect(
        repo_root, resolved_run_id, profile, ci_status_json, branch_warnings
    )
    config = _config_with_include_overrides(config, include_ignored_paths)
    code_quality_scan = create_code_quality_scan(repo_root, scan=scan, config=config)
    package_manager_preflight = build_package_manager_preflight(repo_root, scan)
    resolution_ledger = build_resolution_ledger(
        repo_root=repo_root,
        run_id=resolved_run_id,
        code_quality_scan=code_quality_scan,
        config=config,
    )

    audit_report = build_audit_report(
        scan=scan,
        standards_packet=standards_packet,
        capability_map=capability_map,
        code_quality_scan=code_quality_scan,
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
        "code_quality_scan_json": str(run_dir / "code-quality-scan.json"),
        "package_manager_preflight_json": str(run_dir / "package-manager-preflight.json"),
        "standards_json": str(run_dir / "standards.json"),
        "capability_matrix_json": str(run_dir / "capability-matrix.json"),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
        "quality_audit_json": str(run_dir / "quality-audit.json"),
        "remediation_plan_json": str(run_dir / "remediation-plan.json"),
        "resolution_ledger_json": str(run_dir / "resolution-ledger.json"),
        "resolution_ledger_md": str(run_dir / "resolution-ledger.md"),
        "agent_handoff_json": str(run_dir / "agent-handoff.json"),
        "agent_handoff_md": str(run_dir / "agent-handoff.md"),
    }
    handoff = build_agent_handoff(
        audit_report=audit_report,
        remediation_plan=remediation_plan,
        artifact_paths=artifact_paths,
        capability_map=capability_map,
    )
    _require_valid("agent handoff", validate_agent_handoff(handoff))

    artifact_paths["repo_scan_json"] = str(write_json(run_dir / "repo-scan.json", scan))
    artifact_paths["code_quality_scan_json"] = str(
        write_json(run_dir / "code-quality-scan.json", code_quality_scan)
    )
    artifact_paths["package_manager_preflight_json"] = str(
        write_json(run_dir / "package-manager-preflight.json", package_manager_preflight)
    )
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
    artifact_paths["resolution_ledger_json"] = str(
        write_json(run_dir / "resolution-ledger.json", resolution_ledger)
    )
    artifact_paths["resolution_ledger_md"] = str(
        write_text(
            run_dir / "resolution-ledger.md",
            render_resolution_ledger_markdown(resolution_ledger),
        )
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
        "warnings": _combined_warnings(scan, capability_map),
    }


def verify_gates_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    timeout_seconds: int = 120,
    checkout_most_advanced_branch: bool = False,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    scan, standards_packet, capability_map, config = _inspect(
        repo_root, resolved_run_id, profile, ci_status_json, branch_warnings
    )
    package_manager_preflight = build_package_manager_preflight(repo_root, scan)
    code_quality_scan = create_code_quality_scan(repo_root, scan=scan, config=config)
    gate_verification = verify_discovered_gates(
        repo_root=repo_root,
        capability_map=capability_map,
        run_id=resolved_run_id,
        timeout_seconds=timeout_seconds,
        gate_timeouts=_gate_timeouts(config),
    )
    verified_capability_map = apply_gate_verification(capability_map, gate_verification)
    audit_report = build_audit_report(
        scan=scan,
        standards_packet=standards_packet,
        capability_map=verified_capability_map,
        code_quality_scan=code_quality_scan,
    )
    _require_valid("audit report", validate_audit_report(audit_report))
    remediation_plan = build_remediation_plan(
        audit_report=audit_report,
        capability_map=verified_capability_map,
    )
    _require_valid("remediation plan", validate_remediation_plan(remediation_plan))

    artifact_paths = {
        "repo_scan_json": str(run_dir / "repo-scan.json"),
        "code_quality_scan_json": str(run_dir / "code-quality-scan.json"),
        "package_manager_preflight_json": str(run_dir / "package-manager-preflight.json"),
        "standards_json": str(run_dir / "standards.json"),
        "capability_matrix_json": str(run_dir / "capability-matrix.json"),
        "gate_verification_json": str(run_dir / "gate-verification.json"),
        "quality_audit_json": str(run_dir / "quality-audit.json"),
        "remediation_plan_json": str(run_dir / "remediation-plan.json"),
        "agent_handoff_json": str(run_dir / "agent-handoff.json"),
        "agent_handoff_md": str(run_dir / "agent-handoff.md"),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
    }
    handoff = build_agent_handoff(
        audit_report=audit_report,
        remediation_plan=remediation_plan,
        artifact_paths=artifact_paths,
        capability_map=verified_capability_map,
    )
    _require_valid("agent handoff", validate_agent_handoff(handoff))

    artifact_paths["repo_scan_json"] = str(write_json(run_dir / "repo-scan.json", scan))
    artifact_paths["code_quality_scan_json"] = str(
        write_json(run_dir / "code-quality-scan.json", code_quality_scan)
    )
    artifact_paths["package_manager_preflight_json"] = str(
        write_json(run_dir / "package-manager-preflight.json", package_manager_preflight)
    )
    artifact_paths["standards_json"] = str(write_json(run_dir / "standards.json", standards_packet))
    artifact_paths["capability_matrix_json"] = str(
        write_json(run_dir / "capability-matrix.json", verified_capability_map)
    )
    artifact_paths["gate_verification_json"] = str(
        write_json(run_dir / "gate-verification.json", gate_verification)
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
    run_manifest = build_run_manifest(
        repo_root=repo_root,
        run_id=resolved_run_id,
        mode="verify-gates",
        artifact_paths=artifact_paths,
    )
    artifact_paths["run_manifest_json"] = str(
        write_json(run_dir / "run-manifest.json", run_manifest)
    )

    return {
        "schema": "quality-runner-verify-gates-result-v0.1",
        "status": _verify_payload_status(gate_verification, remediation_plan),
        "implementation_allowed": False,
        "run_id": resolved_run_id,
        "artifact_paths": artifact_paths,
        "warnings": _combined_warnings(scan, verified_capability_map),
    }


def _inspect(
    repo_root: Path,
    run_id: str,
    profile: str | None,
    ci_status_json: Path | None,
    branch_warnings: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    ci_checks, ci_warnings = load_ci_status(repo_root, ci_status_json)
    config = load_repo_config(repo_root)
    scan = inspect_repo(
        repo_root,
        run_id=run_id,
        ci_checks=ci_checks,
        extra_warnings=[*branch_warnings, *ci_warnings],
        config=config,
    )
    resolved_profile = profile or _string_or_default(config.get("default_profile"), DEFAULT_PROFILE)
    standards_packet = compile_standards(
        repo_root=repo_root, scan=scan, profile=resolved_profile, config=config
    )
    capability_map = detect_capabilities(scan=scan, standards_packet=standards_packet)
    return scan, standards_packet, capability_map, config


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


def _config_with_include_overrides(
    config: dict[str, Any],
    include_ignored_paths: list[str] | None,
) -> dict[str, Any]:
    if not include_ignored_paths:
        return config
    merged = dict(config)
    structural_scan = dict(merged.get("structural_scan") or {})
    existing = structural_scan.get("include_ignored_paths")
    paths = (
        [item for item in existing if isinstance(item, str)] if isinstance(existing, list) else []
    )
    for path in include_ignored_paths:
        if path not in paths:
            paths.append(path)
    structural_scan["include_ignored_paths"] = paths
    merged["structural_scan"] = structural_scan
    return merged


def _combined_warnings(
    scan: dict[str, Any], capability_map: dict[str, Any]
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for source in (scan.get("warnings"), capability_map.get("warnings")):
        if not isinstance(source, list):
            continue
        for item in source:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "")
            message = str(item.get("message") or "")
            path = str(item.get("path") or "")
            key = (code, message, path)
            if key in seen:
                continue
            seen.add(key)
            warnings.append(item)
    return warnings


def _gate_timeouts(config: dict[str, Any]) -> dict[str, int]:
    gate_timeouts = config.get("gate_timeouts")
    if not isinstance(gate_timeouts, dict):
        return {}
    return {
        gate_id: seconds
        for gate_id, seconds in gate_timeouts.items()
        if isinstance(gate_id, str) and isinstance(seconds, int) and seconds > 0
    }


def _verify_payload_status(
    gate_verification: dict[str, Any],
    remediation_plan: dict[str, Any],
) -> str:
    gate_status = gate_verification.get("status")
    if gate_status == "passed" and remediation_plan.get("slices"):
        return "passed-with-findings"
    return gate_status if isinstance(gate_status, str) else "blocked"
