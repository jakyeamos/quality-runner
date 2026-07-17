from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from quality_runner.agent_review_policy import AGENT_REVIEW_MODES, AgentReviewMode
from quality_runner.application.read_only_audit import plan_read_only_audit
from quality_runner.artifacts import write_json, write_text
from quality_runner.code_quality import render_resolution_ledger_markdown
from quality_runner.core.audit_contracts import (
    AuditAnalysis,
    AuditArtifactPaths,
    AuditPayload,
    PlannedAudit,
)
from quality_runner.intent import attach_intent_artifacts, intent_for_run
from quality_runner.manifest import build_run_manifest
from quality_runner.module_status import build_module_status
from quality_runner.planning import render_handoff_markdown
from quality_runner.slice_specs import write_slice_specs
from quality_runner.workflow_helpers import add_scan_exclusion_artifact
from quality_runner.workflow_skills import quality_skill_identities, write_skill_review_artifacts


def write_inspect_v1_artifacts(
    analysis: AuditAnalysis,
    *,
    run_dir: Path,
) -> AuditArtifactPaths:
    run_id = analysis.request.run_id
    repo_root = analysis.request.repo_root
    config = _legacy_payload(analysis.config)
    code_quality_scan = _legacy_payload(analysis.code_quality_scan)
    run_intent = intent_for_run(_legacy_optional_payload(analysis.request.intent), run_id)
    module_status = _build_module_status(
        analysis,
        mode="inspect",
        intent=run_intent,
    )
    repo_scan = {**_legacy_payload(analysis.scan), "module_status": module_status}
    scan_exclusion_metadata = _scan_exclusion_metadata(repo_scan)
    artifact_paths: AuditArtifactPaths = {
        "repo_scan_json": str(write_json(run_dir / "repo-scan.json", repo_scan)),
        "code_quality_scan_json": str(
            write_json(run_dir / "code-quality-scan.json", code_quality_scan)
        ),
        "security_scan_json": str(
            write_json(run_dir / "security-scan.json", _legacy_payload(analysis.security_scan))
        ),
        "package_manager_preflight_json": str(
            write_json(
                run_dir / "package-manager-preflight.json",
                _legacy_payload(analysis.package_manager_preflight),
            )
        ),
        "standards_json": str(
            write_json(run_dir / "standards.json", _legacy_payload(analysis.standards_packet))
        ),
        "capability_matrix_json": str(
            write_json(run_dir / "capability-matrix.json", _legacy_payload(analysis.capability_map))
        ),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
    }
    add_scan_exclusion_artifact(artifact_paths, run_dir, scan_exclusion_metadata)
    artifact_paths.update(
        write_skill_review_artifacts(
            run_dir=run_dir,
            run_id=run_id,
            repo_root=repo_root,
            config=config,
            code_quality_scan=code_quality_scan,
            skill_review_report=_legacy_optional_payload(analysis.request.skill_review_report),
            agent_review_mode=_agent_review_mode(analysis),
        )
    )
    artifact_paths = attach_intent_artifacts(
        run_dir=run_dir,
        intent=run_intent,
        artifact_paths=artifact_paths,
    )
    manifest = build_run_manifest(
        repo_root=repo_root,
        run_id=run_id,
        mode="inspect",
        artifact_paths=artifact_paths,
        intent=run_intent,
        quality_skills=quality_skill_identities(code_quality_scan),
        module_status=module_status,
        scan_exclusion_preflight=scan_exclusion_metadata,
    )
    artifact_paths["run_manifest_json"] = str(write_json(run_dir / "run-manifest.json", manifest))
    return artifact_paths


def plan_and_write_run_v1_artifacts(
    analysis: AuditAnalysis,
    *,
    run_dir: Path,
) -> tuple[PlannedAudit, AuditArtifactPaths]:
    run_id = analysis.request.run_id
    repo_root = analysis.request.repo_root
    config = _legacy_payload(analysis.config)
    code_quality_scan = _legacy_payload(analysis.code_quality_scan)
    run_intent = intent_for_run(_legacy_optional_payload(analysis.request.intent), run_id)
    module_status = _build_module_status(
        analysis,
        mode="run",
        intent=run_intent,
    )
    repo_scan = {**_legacy_payload(analysis.scan), "module_status": module_status}
    scan_exclusion_metadata = _scan_exclusion_metadata(repo_scan)
    artifact_paths = _run_artifact_paths(run_dir)
    add_scan_exclusion_artifact(artifact_paths, run_dir, scan_exclusion_metadata)
    artifact_paths.update(
        write_skill_review_artifacts(
            run_dir=run_dir,
            run_id=run_id,
            repo_root=repo_root,
            config=config,
            code_quality_scan=code_quality_scan,
            skill_review_report=_legacy_optional_payload(analysis.request.skill_review_report),
            agent_review_mode=_agent_review_mode(analysis),
        )
    )
    planned = plan_read_only_audit(analysis, artifact_paths=artifact_paths)

    if planned.remediation_context is not None:
        artifact_paths["remediation_context_json"] = str(
            write_json(
                run_dir / "remediation-context.json",
                _legacy_payload(planned.remediation_context),
            )
        )

    artifact_paths["repo_scan_json"] = str(write_json(run_dir / "repo-scan.json", repo_scan))
    artifact_paths["code_quality_scan_json"] = str(
        write_json(run_dir / "code-quality-scan.json", code_quality_scan)
    )
    artifact_paths["security_scan_json"] = str(
        write_json(run_dir / "security-scan.json", _legacy_payload(analysis.security_scan))
    )
    artifact_paths["package_manager_preflight_json"] = str(
        write_json(
            run_dir / "package-manager-preflight.json",
            _legacy_payload(analysis.package_manager_preflight),
        )
    )
    artifact_paths["standards_json"] = str(
        write_json(run_dir / "standards.json", _legacy_payload(analysis.standards_packet))
    )
    artifact_paths["capability_matrix_json"] = str(
        write_json(run_dir / "capability-matrix.json", _legacy_payload(analysis.capability_map))
    )
    artifact_paths = attach_intent_artifacts(
        run_dir=run_dir,
        intent=run_intent,
        artifact_paths=artifact_paths,
    )
    manifest = build_run_manifest(
        repo_root=repo_root,
        run_id=run_id,
        mode="run",
        artifact_paths=artifact_paths,
        intent=run_intent,
        quality_skills=quality_skill_identities(code_quality_scan),
        module_status=module_status,
        scan_exclusion_preflight=scan_exclusion_metadata,
    )
    artifact_paths["run_manifest_json"] = str(write_json(run_dir / "run-manifest.json", manifest))
    artifact_paths["quality_audit_json"] = str(
        write_json(run_dir / "quality-audit.json", _legacy_payload(planned.audit_report))
    )
    remediation_plan = _legacy_payload(planned.remediation_plan)
    artifact_paths["remediation_plan_json"] = str(
        write_json(run_dir / "remediation-plan.json", remediation_plan)
    )
    slice_spec_paths = write_slice_specs(
        run_dir,
        _slices(remediation_plan),
        run_id=run_id,
        intent_docs=_intent_docs(_legacy_payload(analysis.scan)),
    )
    if slice_spec_paths:
        artifact_paths["slice_specs_dir"] = str(run_dir / "slice-specs")
    resolution_ledger = _legacy_payload(planned.resolution_ledger)
    artifact_paths["resolution_ledger_json"] = str(
        write_json(run_dir / "resolution-ledger.json", resolution_ledger)
    )
    artifact_paths["resolution_ledger_md"] = str(
        write_text(
            run_dir / "resolution-ledger.md",
            render_resolution_ledger_markdown(resolution_ledger),
        )
    )
    handoff = _legacy_payload(planned.handoff)
    artifact_paths["agent_handoff_json"] = str(write_json(run_dir / "agent-handoff.json", handoff))
    artifact_paths["agent_handoff_md"] = str(
        write_text(run_dir / "agent-handoff.md", render_handoff_markdown(handoff))
    )
    return planned, artifact_paths


def _build_module_status(
    analysis: AuditAnalysis,
    *,
    mode: str,
    intent: dict[str, Any] | None,
) -> dict[str, Any]:
    standards_packet = _legacy_payload(analysis.standards_packet)
    return build_module_status(
        mode=mode,
        profile=str(standards_packet.get("profile") or "default"),
        repo_scan=_legacy_payload(analysis.scan),
        code_quality_scan=_legacy_payload(analysis.code_quality_scan),
        capability_map=_legacy_payload(analysis.capability_map),
        standards_packet=standards_packet,
        security_scan=_legacy_payload(analysis.security_scan),
        config=_legacy_payload(analysis.config),
        intent=intent,
    )


def _run_artifact_paths(run_dir: Path) -> AuditArtifactPaths:
    return {
        "repo_scan_json": str(run_dir / "repo-scan.json"),
        "code_quality_scan_json": str(run_dir / "code-quality-scan.json"),
        "package_manager_preflight_json": str(run_dir / "package-manager-preflight.json"),
        "standards_json": str(run_dir / "standards.json"),
        "capability_matrix_json": str(run_dir / "capability-matrix.json"),
        "security_scan_json": str(run_dir / "security-scan.json"),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
        "quality_audit_json": str(run_dir / "quality-audit.json"),
        "remediation_plan_json": str(run_dir / "remediation-plan.json"),
        "remediation_context_json": str(run_dir / "remediation-context.json"),
        "resolution_ledger_json": str(run_dir / "resolution-ledger.json"),
        "resolution_ledger_md": str(run_dir / "resolution-ledger.md"),
        "agent_handoff_json": str(run_dir / "agent-handoff.json"),
        "agent_handoff_md": str(run_dir / "agent-handoff.md"),
    }


def _slices(plan: dict[str, Any]) -> list[dict[str, Any]]:
    slices = plan.get("slices")
    return slices if isinstance(slices, list) else []


def _intent_docs(scan: dict[str, Any]) -> list[dict[str, str]] | None:
    intent_docs = scan.get("intent_docs")
    if not isinstance(intent_docs, list):
        return None
    return [item for item in intent_docs if isinstance(item, dict)]


def _legacy_payload(payload: AuditPayload) -> dict[str, Any]:
    return cast(dict[str, Any], payload)


def _legacy_optional_payload(payload: AuditPayload | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return _legacy_payload(payload)


def _scan_exclusion_metadata(scan: dict[str, Any]) -> dict[str, Any] | None:
    metadata = scan.get("scan_exclusion_preflight")
    return metadata if isinstance(metadata, dict) else None


def _agent_review_mode(analysis: AuditAnalysis) -> AgentReviewMode:
    mode = analysis.request.agent_review_mode
    return cast(AgentReviewMode, mode) if mode in AGENT_REVIEW_MODES else "auto"
