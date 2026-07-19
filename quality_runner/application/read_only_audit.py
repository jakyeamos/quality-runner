from __future__ import annotations

from dataclasses import replace
from typing import Any, Literal, cast

from quality_runner.agent_review_policy import (
    AGENT_REVIEW_MODES,
    AgentReviewMode,
    resolve_agent_review_mode,
)
from quality_runner.audit import build_audit_report
from quality_runner.cache_modes import resolve_cache_mode
from quality_runner.capabilities import detect_capabilities
from quality_runner.ci_status import load_ci_status
from quality_runner.code_quality import build_resolution_ledger
from quality_runner.config import load_repo_config
from quality_runner.core.audit_contracts import (
    AuditAnalysis,
    AuditArtifactPaths,
    AuditPayload,
    AuditPlan,
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
from quality_runner.performance import PerformanceRecorder
from quality_runner.planning import build_agent_handoff, build_remediation_plan
from quality_runner.progress import ProgressCallback, emit_progress
from quality_runner.readiness import apply_readiness_evidence_override
from quality_runner.remediation_context import (
    attach_context_refs,
    build_remediation_context_for_plan,
    remediation_context_summary,
    validate_remediation_context,
)
from quality_runner.resolution import resolved_planning_inputs
from quality_runner.scan_scope import create_text_scan_scope
from quality_runner.security.ledger import merge_security_ledger_entries
from quality_runner.security.scan import create_security_scan, merge_security_into_capability_map
from quality_runner.standards import DEFAULT_PROFILE, compile_standards
from quality_runner.workflow_helpers import (
    apply_run_only_scan_exclusion,
    config_with_include_overrides,
    config_with_scan_exclusion_overrides,
)
from quality_runner.workflow_skills import (
    append_warnings,
    create_code_quality_scan_with_skills,
    skill_review_summary,
)


def analyze_read_only_audit(
    request: AuditRequest,
    *,
    progress: ProgressCallback | None = None,
) -> AuditAnalysis:
    repo_root = request.repo_root.expanduser().resolve()
    cache_mode = resolve_cache_mode(request.cache_mode)
    recorder = PerformanceRecorder(
        analysis_mode=request.analysis_mode,
        cache_mode=cache_mode,
        budget_seconds=request.performance_budget_seconds,
    )
    with recorder.stage("discovery"):
        ci_checks, ci_warnings = load_ci_status(repo_root, request.ci_status_json)
        base_config = load_repo_config(repo_root)
        config = config_with_scan_exclusion_overrides(
            base_config,
            request.scan_exclusion_overlay,
        )
        emit_progress(progress, "discovery", "repository facts and scan scope")
        scan = inspect_repo(
            repo_root,
            run_id=request.run_id,
            ci_checks=ci_checks,
            extra_warnings=[*_branch_warnings(request), *ci_warnings],
            config=config,
            cache_mode=cache_mode,
            cache_root=request.cache_root,
        )
    profile = request.profile or _default_profile(config)
    with recorder.stage("standards"):
        emit_progress(progress, "standards", f"profile={profile}")
        standards_packet = compile_standards(
            repo_root=repo_root,
            scan=scan,
            profile=profile,
            config=config,
        )
        capability_map = detect_capabilities(scan=scan, standards_packet=standards_packet)
        capability_map = apply_readiness_evidence_override(
            capability_map=capability_map,
            standards_packet=standards_packet,
            repo_root=repo_root,
            evidence_file=request.readiness_evidence_file,
        )
        config = config_with_include_overrides(config, list(request.include_ignored_paths))
        apply_run_only_scan_exclusion(
            repo_root,
            request.scan_exclusion_overlay,
            config=config,
            scan=scan,
        )
        resolved_agent_review_mode = resolve_agent_review_mode(
            requested=request.agent_review_mode,
            profile=profile,
            config=config,
        )
    with recorder.stage("scope"):
        if request.scan_exclusion_overlay is None:
            text_scan_scope = create_text_scan_scope(
                repo_root,
                scan=scan,
                config=config,
                focus_paths=request.focus_paths,
                read_files=request.analysis_mode == "full",
                cache_mode=cache_mode,
                cache_root=request.cache_root,
            )
            security_scan_scope = text_scan_scope
            code_quality_scan_scope = text_scan_scope
        else:
            text_scan_scope = create_text_scan_scope(
                repo_root,
                scan=scan,
                config=config,
                module="code_quality",
                focus_paths=request.focus_paths,
                read_files=request.analysis_mode == "full",
                cache_mode=cache_mode,
                cache_root=request.cache_root,
            )
            code_quality_scan_scope = text_scan_scope
            security_scan_scope = create_text_scan_scope(
                repo_root,
                scan=scan,
                config=config,
                module="security",
                focus_paths=request.focus_paths,
                read_files=request.analysis_mode == "full",
                cache_mode=cache_mode,
                cache_root=request.cache_root,
            )
        if text_scan_scope.inventory is not None:
            recorder.counters(
                {
                    key: value
                    for key, value in text_scan_scope.inventory.items()
                    if isinstance(value, int)
                }
            )
    with recorder.stage("security"):
        emit_progress(progress, "security", "security surface and dependency analysis")
        security_scan = create_security_scan(
            repo_root,
            scan=scan,
            config=config,
            standards_packet=standards_packet,
            text_scan_scope=security_scan_scope,
            cache_mode=cache_mode,
            cache_root=request.cache_root,
        )
        capability_map = merge_security_into_capability_map(capability_map, security_scan)
    with recorder.stage("code-quality"):
        emit_progress(progress, "code-quality", "structural scan and selected skill packs")
        code_quality_scan, skill_warnings = create_code_quality_scan_with_skills(
            repo_root,
            scan=scan,
            config=config,
            skill_review_report=_legacy_optional_payload(request.skill_review_report),
            require_skill_review_coverage=resolved_agent_review_mode in {"auto", "required"},
            text_scan_scope=code_quality_scan_scope,
            analysis_mode=request.analysis_mode,
            cache_mode=cache_mode,
            cache_root=request.cache_root,
        )
    for deferred in code_quality_scan.get("deferred_checks", []):
        if isinstance(deferred, dict):
            check = deferred.get("check")
            reason = deferred.get("reason")
            severity = deferred.get("severity", "advisory")
            if isinstance(check, str) and isinstance(reason, str) and isinstance(severity, str):
                recorder.defer(check, reason=reason, severity=severity)
    scan = append_warnings(scan, skill_warnings)
    scan["cache_summary"] = _cache_summary(
        scan=scan,
        security_scan=security_scan,
        code_quality_scan=code_quality_scan,
        cache_mode=cache_mode,
    )
    scan["scan_scope"] = {
        "mode": "focused-changed-surface" if request.focus_paths else "repository",
        "paths": list(request.focus_paths),
        "fail_closed_on_empty_focus": bool(request.focus_paths),
        "analysis_mode": request.analysis_mode,
    }
    with recorder.stage("package-preflight"):
        package_manager_preflight = build_package_manager_preflight(repo_root, scan)
    for cache_payload in (security_scan, code_quality_scan):
        cache_evidence = cache_payload.get("analysis_cache")
        if isinstance(cache_evidence, dict):
            cache_hits = _non_negative_int(cache_evidence.get("cache_hits"))
            cache_misses = _non_negative_int(cache_evidence.get("cache_misses"))
            recorder.counters(
                {
                    "cache_hits": cache_hits,
                    "cache_misses": cache_misses,
                    "recomputed_files": _non_negative_int(cache_evidence.get("recomputed_files")),
                    "cache_index_writes": _non_negative_int(cache_evidence.get("index_writes")),
                    "cache_write_failures": _non_negative_int(cache_evidence.get("write_failures")),
                    "source_bytes_read": _non_negative_int(cache_evidence.get("source_bytes_read")),
                }
            )
    performance = recorder.receipt(
        status="partial" if recorder.budget_exceeded else "complete",
        current_phase="package-preflight",
        resume_command=(
            f"quality-runner refresh {repo_root} --run-id-prefix {request.run_id}-resume "
            f"--analysis-mode {request.analysis_mode} --cache-mode {cache_mode}"
            if recorder.budget_exceeded
            else None
        ),
    )
    scan["performance"] = performance
    return AuditAnalysis(
        request=replace(request, agent_review_mode=resolved_agent_review_mode),
        config=_audit_payload(config),
        scan=_audit_payload(scan),
        standards_packet=_audit_payload(standards_packet),
        capability_map=_audit_payload(capability_map),
        security_scan=_audit_payload(security_scan),
        code_quality_scan=_audit_payload(code_quality_scan),
        package_manager_preflight=_audit_payload(package_manager_preflight),
        text_scan_scope=text_scan_scope,
        performance=performance,
    )


def _cache_summary(
    *,
    scan: AuditPayload,
    security_scan: AuditPayload,
    code_quality_scan: AuditPayload,
    cache_mode: str,
) -> dict[str, Any]:
    analyses = {
        name: payload.get("analysis_cache")
        for name, payload in (
            ("security", security_scan),
            ("code_quality", code_quality_scan),
        )
        if isinstance(payload.get("analysis_cache"), dict)
    }
    return {
        "schema": "quality-runner-cache-summary-v0.1",
        "cache_mode": cache_mode,
        "inventory": scan.get("inventory_cache"),
        "analyses": analyses,
        "disabled": cache_mode == "disabled",
        "disabled_reason": "diagnostic-cache-disabled" if cache_mode == "disabled" else None,
    }


def _non_negative_int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


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
    plan = build_audit_plan(
        analysis,
        artifact_paths=artifact_paths,
        resolution_ledger=_audit_payload(resolution_ledger),
    )
    remediation_plan = _legacy_payload(plan.remediation_plan)
    remediation_context = build_remediation_context_for_plan(
        remediation_plan=remediation_plan,
        run_id=analysis.request.run_id,
        repo_root=repo_root,
        repo_scan=_legacy_payload(analysis.scan),
        git_state=git_state_for_repo(repo_root),
    )
    require_valid(
        "remediation context",
        validate_remediation_context(remediation_context, remediation_plan=remediation_plan),
    )
    return PlannedAudit(
        analysis=plan.analysis,
        audit_report=plan.audit_report,
        remediation_plan=plan.remediation_plan,
        handoff=plan.handoff,
        status=plan.status,
        resolution_ledger=_audit_payload(resolution_ledger),
        remediation_context=_audit_payload(remediation_context),
    )


def build_audit_plan(
    analysis: AuditAnalysis,
    *,
    artifact_paths: AuditArtifactPaths,
    gate_verification: AuditPayload | None = None,
    resolution_ledger: AuditPayload | None = None,
) -> AuditPlan:
    repo_root = analysis.request.repo_root.expanduser().resolve()
    code_quality_scan = _legacy_payload(analysis.code_quality_scan)
    security_scan = _legacy_payload(analysis.security_scan)
    audit_report = build_audit_report(
        scan=_legacy_payload(analysis.scan),
        standards_packet=_legacy_payload(analysis.standards_packet),
        capability_map=_legacy_payload(analysis.capability_map),
        code_quality_scan=code_quality_scan,
        security_scan=security_scan,
        resolution_ledger=_legacy_optional_payload(resolution_ledger),
    )
    require_valid("audit report", validate_audit_report(audit_report))
    planning_audit_report, active_code_quality_scan = resolved_planning_inputs(
        audit_report,
        code_quality_scan,
        _legacy_optional_payload(resolution_ledger),
    )
    remediation_plan = build_remediation_plan(
        audit_report=planning_audit_report,
        capability_map=_legacy_payload(analysis.capability_map),
        code_quality_scan=active_code_quality_scan,
        repo_root=repo_root,
        git_state=git_state_for_repo(repo_root),
        text_scan_scope=analysis.text_scan_scope,
    )
    require_valid("remediation plan", validate_remediation_plan(remediation_plan))
    remediation_context = build_remediation_context_for_plan(
        remediation_plan=remediation_plan,
        run_id=analysis.request.run_id,
        repo_root=repo_root,
        repo_scan=_legacy_payload(analysis.scan),
        git_state=git_state_for_repo(repo_root),
    )
    require_valid(
        "remediation context",
        validate_remediation_context(remediation_context, remediation_plan=remediation_plan),
    )
    remediation_context_ref = remediation_context_summary(
        remediation_context,
        artifact_path=artifact_paths.get("remediation_context_json"),
    )
    if remediation_context_ref is not None:
        remediation_plan = dict(remediation_plan)
        for collection_name in ("slices", "security_review_slices"):
            collection = remediation_plan.get(collection_name)
            if isinstance(collection, list):
                remediation_plan[collection_name] = attach_context_refs(
                    [item for item in collection if isinstance(item, dict)],
                    remediation_context,
                )
        remediation_plan["remediation_context"] = remediation_context_ref
        require_valid("remediation plan", validate_remediation_plan(remediation_plan))
    skill_review = skill_review_summary(
        code_quality_scan=code_quality_scan,
        artifact_paths=artifact_paths,
        skill_review_report=_legacy_optional_payload(analysis.request.skill_review_report),
        agent_review_mode=_agent_review_mode(analysis),
    )
    handoff = build_agent_handoff(
        audit_report=planning_audit_report,
        remediation_plan=remediation_plan,
        artifact_paths=artifact_paths,
        capability_map=_legacy_payload(analysis.capability_map),
        gate_verification=_legacy_optional_payload(gate_verification),
        security_scan=security_scan,
        intent=intent_for_run(
            _legacy_optional_payload(analysis.request.intent),
            analysis.request.run_id,
        ),
        repo_scan=_legacy_payload(analysis.scan),
        skill_review=skill_review,
    )
    if remediation_context_ref is not None:
        handoff = {**handoff, "remediation_context": remediation_context_ref}
    require_valid("agent handoff", validate_agent_handoff(handoff))
    status: Literal["clean", "planned"] = (
        "clean" if not remediation_plan.get("slices") else "planned"
    )
    return AuditPlan(
        analysis=analysis,
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


def _agent_review_mode(analysis: AuditAnalysis) -> AgentReviewMode:
    mode = analysis.request.agent_review_mode
    return cast(AgentReviewMode, mode) if mode in AGENT_REVIEW_MODES else "auto"
