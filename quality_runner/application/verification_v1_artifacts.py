from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from quality_runner.agent_review_policy import AGENT_REVIEW_MODES, AgentReviewMode
from quality_runner.application.performance_artifacts import write_performance_artifact
from quality_runner.artifacts import prepare_directory, safe_child_file, write_json, write_text
from quality_runner.core.audit_contracts import (
    AuditAnalysis,
    AuditArtifactPaths,
    AuditPayload,
    AuditPlan,
)
from quality_runner.core.verification_contracts import GateExecutionPlan, GateVerificationPayload
from quality_runner.intent import attach_intent_artifacts, intent_for_run
from quality_runner.manifest import build_run_manifest
from quality_runner.planning import render_handoff_markdown
from quality_runner.remediation_context import build_remediation_context_for_plan
from quality_runner.security.review_obligations import build_security_review_obligations
from quality_runner.slice_specs import write_slice_specs
from quality_runner.workflow_helpers import add_scan_exclusion_artifact
from quality_runner.workflow_skills import quality_skill_identities, write_skill_review_artifacts


def prepare_verification_v1_artifacts(
    analysis: AuditAnalysis,
    *,
    run_dir: Path,
) -> AuditArtifactPaths:
    artifact_paths = _artifact_paths(run_dir)
    add_scan_exclusion_artifact(
        artifact_paths,
        run_dir,
        _scan_exclusion_metadata(_legacy_payload(analysis.scan)),
    )
    artifact_paths.update(
        write_skill_review_artifacts(
            run_dir=run_dir,
            run_id=analysis.request.run_id,
            repo_root=analysis.request.repo_root,
            config=_legacy_payload(analysis.config),
            code_quality_scan=_legacy_payload(analysis.code_quality_scan),
            skill_review_report=_legacy_optional_payload(analysis.request.skill_review_report),
            agent_review_mode=_agent_review_mode(analysis),
        )
    )
    write_performance_artifact(
        analysis,
        run_dir=run_dir,
        artifact_paths=artifact_paths,
    )
    return artifact_paths


def write_gate_execution_plan_v1(
    *,
    run_dir: Path,
    gate_execution_plan: GateExecutionPlan,
) -> None:
    write_json(run_dir / "gate-execution-plan.json", gate_execution_plan)


def write_partial_gate_verification_v1(
    *,
    run_dir: Path,
    gate_verification: GateVerificationPayload,
) -> None:
    write_json(run_dir / "gate-verification.json", _legacy_payload(gate_verification))


def write_completed_verification_v1_artifacts(
    *,
    analysis: AuditAnalysis,
    run_dir: Path,
    artifact_paths: AuditArtifactPaths,
    gate_execution_plan: GateExecutionPlan,
    gate_verification: GateVerificationPayload,
    verified_capability_map: AuditPayload,
    code_quality_scan: AuditPayload,
    planned_audit: AuditPlan,
) -> AuditArtifactPaths:
    artifact_paths["repo_scan_json"] = str(
        write_json(run_dir / "repo-scan.json", _legacy_payload(analysis.scan))
    )
    artifact_paths["code_quality_scan_json"] = str(
        write_json(run_dir / "code-quality-scan.json", _legacy_payload(code_quality_scan))
    )
    artifact_paths["security_scan_json"] = str(
        write_json(run_dir / "security-scan.json", _legacy_payload(analysis.security_scan))
    )
    artifact_paths["security_review_obligations_json"] = str(
        write_json(
            run_dir / "security-review-obligations.json",
            build_security_review_obligations(_legacy_payload(analysis.security_scan)),
        )
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
        write_json(run_dir / "capability-matrix.json", _legacy_payload(verified_capability_map))
    )
    artifact_paths["gate_execution_plan_json"] = str(
        write_json(run_dir / "gate-execution-plan.json", gate_execution_plan)
    )
    artifact_paths["gate_verification_json"] = str(
        write_json(run_dir / "gate-verification.json", _legacy_payload(gate_verification))
    )
    artifact_paths["quality_audit_json"] = str(
        write_json(run_dir / "quality-audit.json", _legacy_payload(planned_audit.audit_report))
    )
    remediation_plan = _legacy_payload(planned_audit.remediation_plan)
    artifact_paths["remediation_context_json"] = str(
        write_json(
            run_dir / "remediation-context.json",
            build_remediation_context_for_plan(
                remediation_plan=remediation_plan,
                run_id=analysis.request.run_id,
                repo_root=analysis.request.repo_root,
                repo_scan=_legacy_payload(analysis.scan),
            ),
        )
    )
    artifact_paths["remediation_plan_json"] = str(
        write_json(run_dir / "remediation-plan.json", remediation_plan)
    )
    slice_spec_paths = write_slice_specs(
        run_dir,
        _slices(remediation_plan),
        run_id=analysis.request.run_id,
        intent_docs=_intent_docs(_legacy_payload(analysis.scan)),
    )
    if slice_spec_paths:
        artifact_paths["slice_specs_dir"] = str(run_dir / "slice-specs")
    security_slice_paths = write_security_review_slice_specs(
        run_dir,
        build_security_review_obligations(_legacy_payload(analysis.security_scan)),
        run_id=analysis.request.run_id,
    )
    if security_slice_paths:
        artifact_paths["security_review_slice_specs_dir"] = str(
            run_dir / "security-review-slice-specs"
        )
    handoff = _legacy_payload(planned_audit.handoff)
    artifact_paths["agent_handoff_json"] = str(write_json(run_dir / "agent-handoff.json", handoff))
    artifact_paths["agent_handoff_md"] = str(
        write_text(run_dir / "agent-handoff.md", render_handoff_markdown(handoff))
    )
    run_intent = intent_for_run(
        _legacy_optional_payload(analysis.request.intent), analysis.request.run_id
    )
    artifact_paths = attach_intent_artifacts(
        run_dir=run_dir,
        intent=run_intent,
        artifact_paths=artifact_paths,
    )
    manifest = build_run_manifest(
        repo_root=analysis.request.repo_root,
        run_id=analysis.request.run_id,
        mode="verify-gates",
        artifact_paths=artifact_paths,
        intent=run_intent,
        quality_skills=quality_skill_identities(_legacy_payload(code_quality_scan)),
        scan_exclusion_preflight=_scan_exclusion_metadata(_legacy_payload(analysis.scan)),
    )
    artifact_paths["run_manifest_json"] = str(write_json(run_dir / "run-manifest.json", manifest))
    return artifact_paths


def write_security_review_slice_specs(
    run_dir: Path,
    obligations_payload: dict[str, Any],
    *,
    run_id: str,
) -> dict[str, str]:
    obligations = obligations_payload.get("obligations")
    if not isinstance(obligations, list):
        return {}
    specs_dir = prepare_directory(run_dir, "security-review-slice-specs")
    paths: dict[str, str] = {}
    for obligation in obligations:
        if not isinstance(obligation, dict):
            continue
        obligation_id = obligation.get("id")
        if not isinstance(obligation_id, str) or not obligation_id:
            continue
        slice_id = f"security-review-{obligation_id}"
        refs = obligation.get("candidate_refs")
        lines = [
            f"# Security Review Slice: {slice_id}",
            "",
            f"- Run: `{run_id}`",
            f"- Finding: `{obligation.get('finding_id')}`",
            f"- Status: `{obligation.get('status')}`",
            "",
            "## Review contract",
            "",
            *[
                f"- {item}"
                for item in obligation.get("review_instructions", [])
                if isinstance(item, str)
            ],
            "",
            "## Exact candidate references",
            "",
        ]
        if isinstance(refs, list) and refs:
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                file = ref.get("file")
                line = ref.get("line")
                location = (
                    f"{file}:{line}"
                    if isinstance(file, str) and isinstance(line, int)
                    else str(file or "unknown")
                )
                lines.append(f"- `{location}` ({ref.get('category', 'uncategorized')})")
        else:
            lines.append(
                "- No specific candidate reference was produced; review the stated scope and record that limitation."
            )
        lines.extend(["", "## Completion criteria", ""])
        lines.extend(
            f"- {item}"
            for item in obligation.get("completion_criteria", [])
            if isinstance(item, str)
        )
        target = safe_child_file(specs_dir, f"{slice_id}.md")
        paths[slice_id] = str(write_text(target, "\n".join(lines).rstrip() + "\n"))
    return paths


def _artifact_paths(run_dir: Path) -> AuditArtifactPaths:
    return {
        "repo_scan_json": str(run_dir / "repo-scan.json"),
        "code_quality_scan_json": str(run_dir / "code-quality-scan.json"),
        "security_scan_json": str(run_dir / "security-scan.json"),
        "security_review_obligations_json": str(run_dir / "security-review-obligations.json"),
        "package_manager_preflight_json": str(run_dir / "package-manager-preflight.json"),
        "standards_json": str(run_dir / "standards.json"),
        "capability_matrix_json": str(run_dir / "capability-matrix.json"),
        "gate_execution_plan_json": str(run_dir / "gate-execution-plan.json"),
        "gate_verification_json": str(run_dir / "gate-verification.json"),
        "quality_audit_json": str(run_dir / "quality-audit.json"),
        "remediation_plan_json": str(run_dir / "remediation-plan.json"),
        "remediation_context_json": str(run_dir / "remediation-context.json"),
        "agent_handoff_json": str(run_dir / "agent-handoff.json"),
        "agent_handoff_md": str(run_dir / "agent-handoff.md"),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
        "performance_json": str(run_dir / "performance.json"),
    }


def _slices(plan: dict[str, Any]) -> list[dict[str, Any]]:
    slices = plan.get("slices")
    return slices if isinstance(slices, list) else []


def _intent_docs(scan: dict[str, Any]) -> list[dict[str, str]] | None:
    intent_docs = scan.get("intent_docs")
    if not isinstance(intent_docs, list):
        return None
    return [item for item in intent_docs if isinstance(item, dict)]


def _legacy_payload(payload: AuditPayload | GateVerificationPayload) -> dict[str, Any]:
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
