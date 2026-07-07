from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.audit import build_audit_report
from quality_runner.code_quality import (
    build_resolution_ledger,
    render_resolution_ledger_markdown,
)
from quality_runner.findings import (
    validate_agent_handoff,
    validate_audit_report,
    validate_remediation_plan,
)
from quality_runner.git_branches import prepare_scan_branch
from quality_runner.intent import attach_intent_artifacts, intent_for_run
from quality_runner.manifest import build_run_manifest
from quality_runner.package_preflight import build_package_manager_preflight
from quality_runner.planning import (
    build_agent_handoff,
    build_remediation_plan,
    render_handoff_markdown,
)
from quality_runner.refresh_workflow import run_refresh_payload
from quality_runner.run_summary import build_run_summary
from quality_runner.security.ledger import merge_security_ledger_entries
from quality_runner.security.scan import create_security_scan, merge_security_into_capability_map
from quality_runner.workflow_helpers import (
    combined_warnings,
    config_with_include_overrides,
)
from quality_runner.workflow_internal import generated_run_id, inspect_repo_bundle, require_valid
from quality_runner.workflow_skills import (
    append_warnings,
    create_code_quality_scan_with_skills,
    write_skill_review_artifacts,
)
from quality_runner.workflow_verify import verify_gates_payload


def inspect_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    include_ignored_paths: list[str] | None = None,
    checkout_most_advanced_branch: bool = False,
    skill_review_report: dict[str, Any] | None = None,
    intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    scan, standards_packet, capability_map, config = inspect_repo_bundle(
        repo_root, resolved_run_id, profile, ci_status_json, branch_warnings
    )
    config = config_with_include_overrides(config, include_ignored_paths)
    security_scan = create_security_scan(
        repo_root,
        scan=scan,
        config=config,
        standards_packet=standards_packet,
    )
    capability_map = merge_security_into_capability_map(capability_map, security_scan)
    code_quality_scan, skill_warnings = create_code_quality_scan_with_skills(
        repo_root,
        scan=scan,
        config=config,
        skill_review_report=skill_review_report,
    )
    scan = append_warnings(scan, skill_warnings)
    package_manager_preflight = build_package_manager_preflight(repo_root, scan)

    artifact_paths = {
        "repo_scan_json": str(write_json(run_dir / "repo-scan.json", scan)),
        "code_quality_scan_json": str(
            write_json(run_dir / "code-quality-scan.json", code_quality_scan)
        ),
        "security_scan_json": str(write_json(run_dir / "security-scan.json", security_scan)),
        "package_manager_preflight_json": str(
            write_json(run_dir / "package-manager-preflight.json", package_manager_preflight)
        ),
        "standards_json": str(write_json(run_dir / "standards.json", standards_packet)),
        "capability_matrix_json": str(
            write_json(run_dir / "capability-matrix.json", capability_map)
        ),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
    }
    artifact_paths.update(
        write_skill_review_artifacts(
            run_dir=run_dir,
            run_id=resolved_run_id,
            repo_root=repo_root,
            config=config,
            code_quality_scan=code_quality_scan,
            skill_review_report=skill_review_report,
        )
    )
    run_intent = intent_for_run(intent, resolved_run_id)
    artifact_paths = attach_intent_artifacts(
        run_dir=run_dir,
        intent=run_intent,
        artifact_paths=artifact_paths,
    )
    inspect_manifest = build_run_manifest(
        repo_root=repo_root,
        run_id=resolved_run_id,
        mode="inspect",
        artifact_paths=artifact_paths,
        intent=run_intent,
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
        "warnings": combined_warnings(scan, capability_map),
    }


def run_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    include_ignored_paths: list[str] | None = None,
    checkout_most_advanced_branch: bool = False,
    skill_review_report: dict[str, Any] | None = None,
    intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    scan, standards_packet, capability_map, config = inspect_repo_bundle(
        repo_root, resolved_run_id, profile, ci_status_json, branch_warnings
    )
    config = config_with_include_overrides(config, include_ignored_paths)
    security_scan = create_security_scan(
        repo_root,
        scan=scan,
        config=config,
        standards_packet=standards_packet,
    )
    capability_map = merge_security_into_capability_map(capability_map, security_scan)
    code_quality_scan, skill_warnings = create_code_quality_scan_with_skills(
        repo_root,
        scan=scan,
        config=config,
        skill_review_report=skill_review_report,
    )
    scan = append_warnings(scan, skill_warnings)
    package_manager_preflight = build_package_manager_preflight(repo_root, scan)
    resolution_ledger = build_resolution_ledger(
        repo_root=repo_root,
        run_id=resolved_run_id,
        code_quality_scan=code_quality_scan,
        config=config,
    )
    resolution_ledger = merge_security_ledger_entries(
        resolution_ledger,
        security_scan=security_scan,
        config=config,
        repo_root=repo_root,
        run_id=resolved_run_id,
    )

    audit_report = build_audit_report(
        scan=scan,
        standards_packet=standards_packet,
        capability_map=capability_map,
        code_quality_scan=code_quality_scan,
        security_scan=security_scan,
    )
    require_valid("audit report", validate_audit_report(audit_report))

    remediation_plan = build_remediation_plan(
        audit_report=audit_report,
        capability_map=capability_map,
        code_quality_scan=code_quality_scan,
    )
    require_valid("remediation plan", validate_remediation_plan(remediation_plan))
    status = "clean" if not remediation_plan["slices"] else "planned"

    artifact_paths = {
        "repo_scan_json": str(run_dir / "repo-scan.json"),
        "code_quality_scan_json": str(run_dir / "code-quality-scan.json"),
        "package_manager_preflight_json": str(run_dir / "package-manager-preflight.json"),
        "standards_json": str(run_dir / "standards.json"),
        "capability_matrix_json": str(run_dir / "capability-matrix.json"),
        "security_scan_json": str(run_dir / "security-scan.json"),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
        "quality_audit_json": str(run_dir / "quality-audit.json"),
        "remediation_plan_json": str(run_dir / "remediation-plan.json"),
        "resolution_ledger_json": str(run_dir / "resolution-ledger.json"),
        "resolution_ledger_md": str(run_dir / "resolution-ledger.md"),
        "agent_handoff_json": str(run_dir / "agent-handoff.json"),
        "agent_handoff_md": str(run_dir / "agent-handoff.md"),
    }
    artifact_paths.update(
        write_skill_review_artifacts(
            run_dir=run_dir,
            run_id=resolved_run_id,
            repo_root=repo_root,
            config=config,
            code_quality_scan=code_quality_scan,
            skill_review_report=skill_review_report,
        )
    )
    handoff = build_agent_handoff(
        audit_report=audit_report,
        remediation_plan=remediation_plan,
        artifact_paths=artifact_paths,
        capability_map=capability_map,
        security_scan=security_scan,
        intent=intent_for_run(intent, resolved_run_id),
        repo_scan=scan,
    )
    require_valid("agent handoff", validate_agent_handoff(handoff))

    artifact_paths["repo_scan_json"] = str(write_json(run_dir / "repo-scan.json", scan))
    artifact_paths["code_quality_scan_json"] = str(
        write_json(run_dir / "code-quality-scan.json", code_quality_scan)
    )
    artifact_paths["security_scan_json"] = str(
        write_json(run_dir / "security-scan.json", security_scan)
    )
    artifact_paths["package_manager_preflight_json"] = str(
        write_json(run_dir / "package-manager-preflight.json", package_manager_preflight)
    )
    artifact_paths["standards_json"] = str(write_json(run_dir / "standards.json", standards_packet))
    artifact_paths["capability_matrix_json"] = str(
        write_json(run_dir / "capability-matrix.json", capability_map)
    )
    run_intent = intent_for_run(intent, resolved_run_id)
    artifact_paths = attach_intent_artifacts(
        run_dir=run_dir,
        intent=run_intent,
        artifact_paths=artifact_paths,
    )
    run_manifest = build_run_manifest(
        repo_root=repo_root,
        run_id=resolved_run_id,
        mode="run",
        artifact_paths=artifact_paths,
        intent=run_intent,
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
        "warnings": combined_warnings(scan, capability_map),
    }


def refresh_payload(
    repo_root: Path,
    run_id_prefix: str,
    baseline_run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    timeout_seconds: int = 120,
    workflow_timeout_seconds: int | None = None,
    verify_timeout_seconds: int | None = None,
    workflow_timeout_reason: str | None = None,
    total_timeout_seconds: int | None = None,
    total_timeout_reason: str | None = None,
    checkout_most_advanced_branch: bool = False,
    allow_mutating_gates: bool = False,
    worktree_mode: str = "in-place",
    allow_dirty_worktree_verify: bool = False,
    intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return run_refresh_payload(
        repo_root=repo_root,
        run_id_prefix=run_id_prefix,
        baseline_run_id=baseline_run_id,
        profile=profile,
        ci_status_json=ci_status_json,
        timeout_seconds=timeout_seconds,
        workflow_timeout_seconds=workflow_timeout_seconds,
        verify_timeout_seconds=verify_timeout_seconds,
        workflow_timeout_reason=workflow_timeout_reason,
        total_timeout_seconds=total_timeout_seconds,
        total_timeout_reason=total_timeout_reason,
        checkout_most_advanced_branch=checkout_most_advanced_branch,
        allow_mutating_gates=allow_mutating_gates,
        worktree_mode=worktree_mode,
        allow_dirty_worktree_verify=allow_dirty_worktree_verify,
        intent=intent,
        inspect_callback=inspect_payload,
        run_callback=run_payload,
        verify_callback=verify_gates_payload,
        summary_callback=build_run_summary,
    )

