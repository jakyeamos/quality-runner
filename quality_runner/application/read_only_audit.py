from __future__ import annotations

from typing import Any, Literal, cast

from quality_runner.audit import build_audit_report
from quality_runner.capabilities import detect_capabilities
from quality_runner.ci_status import load_ci_status
from quality_runner.code_quality import build_resolution_ledger
from quality_runner.config import load_repo_config
from quality_runner.core.audit_contracts import (
    AuditAnalysis,
    AuditArtifactPaths,
    AuditPayload,
    AuditRequest,
    PlannedAudit,
)
from quality_runner.discovery import inspect_repo
from quality_runner.findings import (
    require_valid,
    validate_agent_handoff,
    validate_audit_report,
    validate_remediation_plan,
)
from quality_runner.gate_resolution_bridge import merge_gate_finding_dispositions
from quality_runner.intent import intent_for_run
from quality_runner.manifest import git_state_for_repo
from quality_runner.package_preflight import build_package_manager_preflight
from quality_runner.planning import build_agent_handoff, build_remediation_plan
from quality_runner.scan_scope import create_text_scan_scope
from quality_runner.security.ledger import merge_security_ledger_entries
from quality_runner.security.scan import create_security_scan, merge_security_into_capability_map
from quality_runner.standards import DEFAULT_PROFILE, compile_standards
from quality_runner.workflow_helpers import config_with_include_overrides
from quality_runner.workflow_skills import append_warnings, create_code_quality_scan_with_skills


def analyze_read_only_audit(request: AuditRequest) -> AuditAnalysis:
    repo_root = request.repo_root.expanduser().resolve()
    ci_checks, ci_warnings = load_ci_status(repo_root, request.ci_status_json)
    base_config = load_repo_config(repo_root)
    scan = inspect_repo(
        repo_root,
        run_id=request.run_id,
        ci_checks=ci_checks,
        extra_warnings=[*_branch_warnings(request), *ci_warnings],
        config=base_config,
    )
    profile = request.profile or _default_profile(base_config)
    standards_packet = compile_standards(
        repo_root=repo_root,
        scan=scan,
        profile=profile,
        config=base_config,
    )
    capability_map = detect_capabilities(scan=scan, standards_packet=standards_packet)
    config = config_with_include_overrides(base_config, list(request.include_ignored_paths))
    text_scan_scope = create_text_scan_scope(repo_root, scan=scan, config=config)
    security_scan = create_security_scan(
        repo_root,
        scan=scan,
        config=config,
        standards_packet=standards_packet,
        text_scan_scope=text_scan_scope,
    )
    capability_map = merge_security_into_capability_map(capability_map, security_scan)
    code_quality_scan, skill_warnings = create_code_quality_scan_with_skills(
        repo_root,
        scan=scan,
        config=config,
        skill_review_report=_legacy_optional_payload(request.skill_review_report),
        text_scan_scope=text_scan_scope,
    )
    scan = append_warnings(scan, skill_warnings)
    package_manager_preflight = build_package_manager_preflight(repo_root, scan)
    return AuditAnalysis(
        request=request,
        config=_audit_payload(config),
        scan=_audit_payload(scan),
        standards_packet=_audit_payload(standards_packet),
        capability_map=_audit_payload(capability_map),
        security_scan=_audit_payload(security_scan),
        code_quality_scan=_audit_payload(code_quality_scan),
        package_manager_preflight=_audit_payload(package_manager_preflight),
        text_scan_scope=text_scan_scope,
    )


def plan_read_only_audit(
    analysis: AuditAnalysis,
    *,
    artifact_paths: AuditArtifactPaths,
) -> PlannedAudit:
    repo_root = analysis.request.repo_root.expanduser().resolve()
    config = _legacy_payload(analysis.config)
    code_quality_scan = _legacy_payload(analysis.code_quality_scan)
    security_scan = _legacy_payload(analysis.security_scan)
    resolution_ledger = build_resolution_ledger(
        repo_root=repo_root,
        run_id=analysis.request.run_id,
        code_quality_scan=code_quality_scan,
        config=config,
    )
    resolution_ledger = merge_security_ledger_entries(
        resolution_ledger,
        security_scan=security_scan,
        config=config,
        repo_root=repo_root,
        run_id=analysis.request.run_id,
    )
    resolution_ledger = merge_gate_finding_dispositions(
        resolution_ledger,
        repo_root=repo_root,
        run_id=analysis.request.run_id,
    )
    audit_report = build_audit_report(
        scan=_legacy_payload(analysis.scan),
        standards_packet=_legacy_payload(analysis.standards_packet),
        capability_map=_legacy_payload(analysis.capability_map),
        code_quality_scan=code_quality_scan,
        security_scan=security_scan,
    )
    require_valid("audit report", validate_audit_report(audit_report))
    remediation_plan = build_remediation_plan(
        audit_report=audit_report,
        capability_map=_legacy_payload(analysis.capability_map),
        code_quality_scan=code_quality_scan,
        repo_root=repo_root,
        git_state=git_state_for_repo(repo_root),
    )
    require_valid("remediation plan", validate_remediation_plan(remediation_plan))
    handoff = build_agent_handoff(
        audit_report=audit_report,
        remediation_plan=remediation_plan,
        artifact_paths=artifact_paths,
        capability_map=_legacy_payload(analysis.capability_map),
        security_scan=security_scan,
        intent=intent_for_run(
            _legacy_optional_payload(analysis.request.intent),
            analysis.request.run_id,
        ),
        repo_scan=_legacy_payload(analysis.scan),
    )
    require_valid("agent handoff", validate_agent_handoff(handoff))
    status: Literal["clean", "planned"] = (
        "clean" if not remediation_plan.get("slices") else "planned"
    )
    return PlannedAudit(
        analysis=analysis,
        resolution_ledger=_audit_payload(resolution_ledger),
        audit_report=_audit_payload(audit_report),
        remediation_plan=_audit_payload(remediation_plan),
        handoff=_audit_payload(handoff),
        status=status,
    )


def _branch_warnings(request: AuditRequest) -> list[dict[str, str]]:
    return [
        {
            "code": warning["code"],
            "message": warning["message"],
            "path": warning["path"],
        }
        for warning in request.branch_warnings
    ]


def _default_profile(config: dict[str, Any]) -> str:
    value = config.get("default_profile")
    return value if isinstance(value, str) and value else DEFAULT_PROFILE


def _audit_payload(payload: dict[str, Any]) -> AuditPayload:
    return cast(AuditPayload, payload)


def _legacy_payload(payload: AuditPayload) -> dict[str, Any]:
    return cast(dict[str, Any], payload)


def _legacy_optional_payload(payload: AuditPayload | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return _legacy_payload(payload)
