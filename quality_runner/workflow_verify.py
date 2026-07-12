from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.audit import build_audit_report
from quality_runner.findings import (
    require_valid,
    validate_agent_handoff,
    validate_audit_report,
    validate_remediation_plan,
)
from quality_runner.gate_verification import (
    apply_gate_verification,
    build_gate_execution_plan,
    verify_discovered_gates,
)
from quality_runner.git_branches import prepare_scan_branch
from quality_runner.intent import attach_intent_artifacts, intent_for_run
from quality_runner.manifest import build_run_manifest, git_state_for_repo
from quality_runner.package_preflight import build_package_manager_preflight
from quality_runner.planning import (
    build_agent_handoff,
    build_remediation_plan,
    render_handoff_markdown,
)
from quality_runner.security.scan import create_security_scan, merge_security_into_capability_map
from quality_runner.slice_specs import write_slice_specs
from quality_runner.unwired_from_dead_code import merge_dead_code_unwired_findings
from quality_runner.workflow_helpers import (
    combined_warnings,
    config_with_include_overrides,
    gate_timeouts,
)
from quality_runner.workflow_internal import (
    generated_run_id,
    inspect_repo_bundle,
    verify_payload_status,
)
from quality_runner.workflow_skills import (
    append_warnings,
    create_code_quality_scan_with_skills,
    write_skill_review_artifacts,
)
from quality_runner.worktree_verify import gate_worktree_session, resolve_worktree_mode


def verify_gates_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    timeout_seconds: int = 120,
    checkout_most_advanced_branch: bool = False,
    execute_discovered_gates: bool = False,
    read_only_gates: bool = False,
    allow_mutating_gates: bool = False,
    worktree_mode: str = "in-place",
    allow_dirty_worktree_verify: bool = False,
    skill_review_report: dict[str, Any] | None = None,
    intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_worktree_mode = resolve_worktree_mode(worktree_mode)
    if execute_discovered_gates and resolved_worktree_mode != "disposable":
        raise ValueError(
            "executing discovered gates requires --worktree-mode disposable to isolate the target repository"
        )
    resolved_run_id = generated_run_id() if run_id is None else run_id
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    scan, standards_packet, capability_map, config = inspect_repo_bundle(
        repo_root, resolved_run_id, profile, ci_status_json, branch_warnings
    )
    config = config_with_include_overrides(config, None)
    security_scan = create_security_scan(
        repo_root,
        scan=scan,
        config=config,
        standards_packet=standards_packet,
    )
    capability_map = merge_security_into_capability_map(capability_map, security_scan)
    package_manager_preflight = build_package_manager_preflight(repo_root, scan)
    code_quality_scan, skill_warnings = create_code_quality_scan_with_skills(
        repo_root,
        scan=scan,
        config=config,
        skill_review_report=skill_review_report,
    )
    scan = append_warnings(scan, skill_warnings)
    artifact_paths = {
        "repo_scan_json": str(run_dir / "repo-scan.json"),
        "code_quality_scan_json": str(run_dir / "code-quality-scan.json"),
        "security_scan_json": str(run_dir / "security-scan.json"),
        "package_manager_preflight_json": str(run_dir / "package-manager-preflight.json"),
        "standards_json": str(run_dir / "standards.json"),
        "capability_matrix_json": str(run_dir / "capability-matrix.json"),
        "gate_execution_plan_json": str(run_dir / "gate-execution-plan.json"),
        "gate_verification_json": str(run_dir / "gate-verification.json"),
        "quality_audit_json": str(run_dir / "quality-audit.json"),
        "remediation_plan_json": str(run_dir / "remediation-plan.json"),
        "agent_handoff_json": str(run_dir / "agent-handoff.json"),
        "agent_handoff_md": str(run_dir / "agent-handoff.md"),
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

    def write_partial_gate_verification(verification: dict[str, Any]) -> None:
        write_json(run_dir / "gate-verification.json", verification)

    effective_worktree_mode = resolved_worktree_mode if execute_discovered_gates else "in-place"
    with gate_worktree_session(
        repo_root=repo_root,
        run_id=resolved_run_id,
        worktree_mode=effective_worktree_mode,
        allow_dirty_worktree_verify=allow_dirty_worktree_verify,
    ) as worktree_session:
        verification_context = {
            **worktree_session.verification_context,
            "execution_authorized": execute_discovered_gates,
        }
        gate_execution_plan = build_gate_execution_plan(
            repo_root=worktree_session.execution_root,
            capability_map=capability_map,
            timeout_seconds=timeout_seconds,
            gate_timeouts=gate_timeouts(config),
            execute_discovered_gates=execute_discovered_gates,
            read_only_gates=read_only_gates,
            allow_mutating_gates=allow_mutating_gates,
            mutations_isolated=worktree_session.mutations_isolated,
        )
        write_json(run_dir / "gate-execution-plan.json", gate_execution_plan)
        gate_verification = verify_discovered_gates(
            repo_root=repo_root,
            capability_map=capability_map,
            run_id=resolved_run_id,
            timeout_seconds=timeout_seconds,
            gate_timeouts=gate_timeouts(config),
            execute_discovered_gates=execute_discovered_gates,
            read_only_gates=read_only_gates,
            allow_mutating_gates=allow_mutating_gates,
            execution_root=worktree_session.execution_root,
            mutations_isolated=worktree_session.mutations_isolated,
            verification_context=verification_context,
            on_partial_result=write_partial_gate_verification,
        )
    verified_capability_map = apply_gate_verification(capability_map, gate_verification)
    code_quality_scan = merge_dead_code_unwired_findings(
        code_quality_scan,
        gate_verification,
        config,
    )
    audit_report = build_audit_report(
        scan=scan,
        standards_packet=standards_packet,
        capability_map=verified_capability_map,
        code_quality_scan=code_quality_scan,
        security_scan=security_scan,
    )
    require_valid("audit report", validate_audit_report(audit_report))
    remediation_plan = build_remediation_plan(
        audit_report=audit_report,
        capability_map=verified_capability_map,
        code_quality_scan=code_quality_scan,
        repo_root=repo_root,
        git_state=git_state_for_repo(repo_root),
    )
    require_valid("remediation plan", validate_remediation_plan(remediation_plan))

    handoff = build_agent_handoff(
        audit_report=audit_report,
        remediation_plan=remediation_plan,
        artifact_paths=artifact_paths,
        capability_map=verified_capability_map,
        gate_verification=gate_verification,
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
        write_json(run_dir / "capability-matrix.json", verified_capability_map)
    )
    artifact_paths["gate_execution_plan_json"] = str(
        write_json(run_dir / "gate-execution-plan.json", gate_execution_plan)
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
    slice_spec_paths = write_slice_specs(
        run_dir,
        remediation_plan.get("slices", []),
        run_id=resolved_run_id,
        intent_docs=scan.get("intent_docs") if isinstance(scan.get("intent_docs"), list) else None,
    )
    if slice_spec_paths:
        artifact_paths["slice_specs_dir"] = str(run_dir / "slice-specs")
    artifact_paths["agent_handoff_json"] = str(write_json(run_dir / "agent-handoff.json", handoff))
    artifact_paths["agent_handoff_md"] = str(
        write_text(run_dir / "agent-handoff.md", render_handoff_markdown(handoff))
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
        mode="verify-gates",
        artifact_paths=artifact_paths,
        intent=run_intent,
    )
    artifact_paths["run_manifest_json"] = str(
        write_json(run_dir / "run-manifest.json", run_manifest)
    )

    return {
        "schema": "quality-runner-verify-gates-result-v0.1",
        "status": verify_payload_status(gate_verification, remediation_plan),
        "implementation_allowed": False,
        "run_id": resolved_run_id,
        "artifact_paths": artifact_paths,
        "warnings": combined_warnings(scan, verified_capability_map),
    }
