from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.agent_review_policy import resolve_agent_review_mode
from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.audit import build_audit_report
from quality_runner.findings import (
    validate_agent_handoff,
    validate_audit_report,
    validate_remediation_plan,
)
from quality_runner.gate_verification import (
    apply_gate_verification,
    build_gate_execution_plan,
    verification_status,
    verify_discovered_gates,
)
from quality_runner.git_branches import prepare_scan_branch
from quality_runner.intent import attach_intent_artifacts, intent_for_run
from quality_runner.manifest import build_run_manifest, git_state_for_repo
from quality_runner.module_status import build_module_status
from quality_runner.package_preflight import build_package_manager_preflight
from quality_runner.planning import (
    build_agent_handoff,
    build_remediation_plan,
    render_handoff_markdown,
)
from quality_runner.progress import ProgressCallback, emit_progress
from quality_runner.readiness import evaluate_readiness
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
    require_valid,
    verify_payload_status,
)
from quality_runner.workflow_skills import (
    append_warnings,
    create_code_quality_scan_with_skills,
    quality_skill_identities,
    skill_review_summary,
    write_skill_review_artifacts,
)
from quality_runner.worktree_verify import gate_worktree_session


def verify_gates_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    readiness_evidence_file: Path | None = None,
    timeout_seconds: int = 120,
    checkout_most_advanced_branch: bool = False,
    read_only_gates: bool = True,
    allow_mutating_gates: bool = False,
    worktree_mode: str = "in-place",
    allow_dirty_worktree_verify: bool = False,
    skill_review_report: dict[str, Any] | None = None,
    agent_review_mode: str | None = None,
    intent: dict[str, Any] | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    emit_progress(progress, "prepare", f"verify-gates run_id={resolved_run_id}")
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    emit_progress(progress, "discovery", "repository facts, configuration, and standards")
    scan, standards_packet, capability_map, config = inspect_repo_bundle(
        repo_root, resolved_run_id, profile, ci_status_json, branch_warnings
    )
    config = config_with_include_overrides(config, None)
    resolved_agent_review_mode = resolve_agent_review_mode(
        requested=agent_review_mode,
        profile=str(standards_packet.get("profile") or profile or "default"),
        config=config,
    )
    emit_progress(progress, "security", "security surface and dependency analysis")
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
        require_skill_review_coverage=resolved_agent_review_mode in {"auto", "required"},
    )
    scan = append_warnings(scan, skill_warnings)
    emit_progress(progress, "gates", "preparing and executing discovered gates")
    run_intent = intent_for_run(intent, resolved_run_id)
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
            agent_review_mode=resolved_agent_review_mode,
            require_skill_review_coverage=resolved_agent_review_mode in {"auto", "required"},
        )
    )

    def write_partial_gate_verification(verification: dict[str, Any]) -> None:
        write_json(run_dir / "gate-verification.json", verification)

    with gate_worktree_session(
        repo_root=repo_root,
        run_id=resolved_run_id,
        worktree_mode=worktree_mode,
        allow_dirty_worktree_verify=allow_dirty_worktree_verify,
    ) as worktree_session:
        gate_execution_plan = build_gate_execution_plan(
            repo_root=worktree_session.execution_root,
            capability_map=capability_map,
            timeout_seconds=timeout_seconds,
            gate_timeouts=gate_timeouts(config),
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
            read_only_gates=read_only_gates,
            allow_mutating_gates=allow_mutating_gates,
            execution_root=worktree_session.execution_root,
            mutations_isolated=worktree_session.mutations_isolated,
            verification_context=worktree_session.verification_context,
            on_partial_result=write_partial_gate_verification,
            scan_exclusions=scan.get("scan_exclusions")
            if isinstance(scan.get("scan_exclusions"), list)
            else None,
        )
    _update_scan_provenance(scan, worktree_session.verification_context)
    verified_capability_map = apply_gate_verification(capability_map, gate_verification)
    readiness = evaluate_readiness(
        repo_root=repo_root,
        scan=scan,
        standards_packet=standards_packet,
        capability_map=verified_capability_map,
        gate_verification=gate_verification,
        verification_context=worktree_session.verification_context,
        evidence_file=readiness_evidence_file,
    )
    emit_progress(progress, "readiness", f"evaluated profile={profile or 'default'}")
    readiness_ids = {
        gate.get("id")
        for gate in readiness.get("gates", [])
        if isinstance(gate, dict) and isinstance(gate.get("id"), str)
    }
    command_readiness_ids = {"package_consumer_smoke", "migration_safety"}
    gate_verification["gates"] = [
        gate
        for gate in gate_verification.get("gates", [])
        if not isinstance(gate, dict)
        or gate.get("id") not in readiness_ids
        or gate.get("id") in command_readiness_ids
    ]
    gate_verification["gates"].extend(readiness.get("gates", []))
    gate_verification["readiness"] = readiness
    gate_verification["status"] = (
        "blocked"
        if readiness.get("status") == "blocked"
        else verification_status(
            [gate for gate in gate_verification["gates"] if isinstance(gate, dict)]
        )
    )
    verified_capability_map = apply_gate_verification(capability_map, gate_verification)
    verified_capability_map["readiness"] = readiness
    code_quality_scan = merge_dead_code_unwired_findings(
        code_quality_scan,
        gate_verification,
        config,
    )
    skill_review = skill_review_summary(
        code_quality_scan=code_quality_scan,
        artifact_paths=artifact_paths,
        skill_review_report=skill_review_report,
        agent_review_mode=resolved_agent_review_mode,
    )
    module_status = build_module_status(
        mode="verify-gates",
        profile=str(standards_packet.get("profile") or profile or "default"),
        repo_scan=scan,
        code_quality_scan=code_quality_scan,
        capability_map=verified_capability_map,
        standards_packet=standards_packet,
        security_scan=security_scan,
        config=config,
        intent=run_intent,
    )
    scan["module_status"] = module_status
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
        intent=run_intent,
        repo_scan=scan,
        skill_review=skill_review,
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
        quality_skills=quality_skill_identities(code_quality_scan),
        module_status=module_status,
        worktree_mode=worktree_session.verification_context.get("worktree_mode", "in-place")
        if isinstance(worktree_session.verification_context, dict)
        else "in-place",
    )
    artifact_paths["run_manifest_json"] = str(
        write_json(run_dir / "run-manifest.json", run_manifest)
    )
    emit_progress(
        progress,
        "complete",
        f"status={gate_verification.get('status', 'completed')} run_id={resolved_run_id}",
    )

    return {
        "schema": "quality-runner-verify-gates-result-v0.1",
        "status": verify_payload_status(
            gate_verification,
            remediation_plan,
            skill_review=skill_review,
        ),
        "implementation_allowed": False,
        "run_id": resolved_run_id,
        "agent_review_mode": resolved_agent_review_mode,
        "artifact_paths": artifact_paths,
        "module_status": module_status,
        **({"skill_review": skill_review} if skill_review is not None else {}),
        "warnings": combined_warnings(scan, verified_capability_map),
    }


def _update_scan_provenance(scan: dict[str, Any], verification_context: dict[str, Any]) -> None:
    worktree_mode = verification_context.get("worktree_mode")
    if not isinstance(worktree_mode, str) or not worktree_mode:
        return
    for key in ("git_provenance", "provenance"):
        provenance = scan.get(key)
        if isinstance(provenance, dict):
            provenance["worktree_mode"] = worktree_mode
