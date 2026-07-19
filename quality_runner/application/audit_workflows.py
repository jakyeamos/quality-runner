from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from quality_runner.agent_review_policy import AGENT_REVIEW_MODES, AgentReviewMode
from quality_runner.application.audit_v1_artifacts import (
    plan_and_write_run_v1_artifacts,
    write_inspect_v1_artifacts,
)
from quality_runner.application.read_only_audit import analyze_read_only_audit
from quality_runner.artifacts import prepare_artifact_dir
from quality_runner.cache_modes import CacheMode
from quality_runner.core.audit_contracts import (
    AnalysisMode,
    AuditPayload,
    AuditRequest,
    AuditWarning,
    ScanExclusionOverlay,
)
from quality_runner.git_branches import prepare_scan_branch
from quality_runner.progress import ProgressCallback
from quality_runner.workflow_helpers import combined_warnings
from quality_runner.workflow_internal import generated_run_id
from quality_runner.workflow_skills import skill_review_summary


def inspect_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    readiness_evidence_file: Path | None = None,
    include_ignored_paths: list[str] | None = None,
    checkout_most_advanced_branch: bool = False,
    skill_review_report: AuditPayload | None = None,
    intent: AuditPayload | None = None,
    agent_review_mode: str | None = None,
    scan_exclusion_overlay: ScanExclusionOverlay | None = None,
    analysis_cache_root: Path | None = None,
    focus_paths: list[str] | None = None,
    analysis_mode: str = "full",
    cache_mode: CacheMode | str | None = None,
    cache_root: Path | None = None,
    performance_budget_seconds: float | None = None,
    progress: ProgressCallback | None = None,
    refresh_context: dict[str, object] | None = None,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    analysis = analyze_read_only_audit(
        _audit_request(
            repo_root=repo_root,
            run_id=resolved_run_id,
            profile=profile,
            ci_status_json=ci_status_json,
            readiness_evidence_file=readiness_evidence_file,
            include_ignored_paths=include_ignored_paths,
            branch_warnings=branch_warnings,
            skill_review_report=skill_review_report,
            agent_review_mode=agent_review_mode,
            scan_exclusion_overlay=scan_exclusion_overlay,
            intent=intent,
            analysis_cache_root=analysis_cache_root,
            focus_paths=focus_paths,
            analysis_mode=analysis_mode,
            cache_mode=cache_mode,
            cache_root=cache_root,
            performance_budget_seconds=performance_budget_seconds,
        ),
        progress=progress,
    )
    _record_refresh_analysis(refresh_context, analysis, source="current-refresh-inspect")
    artifact_paths = write_inspect_v1_artifacts(analysis, run_dir=run_dir)
    skill_review = _skill_review_from_analysis(analysis, artifact_paths)

    return {
        "schema": "quality-runner-inspect-result-v0.1",
        "status": "inspected",
        "implementation_allowed": False,
        "run_id": resolved_run_id,
        "artifact_paths": artifact_paths,
        "module_status": _module_status_from_artifacts(artifact_paths),
        **_optional_field("skill_review", skill_review),
        "warnings": combined_warnings(
            _legacy_payload(analysis.scan), _legacy_payload(analysis.capability_map)
        ),
    }


def run_payload(
    repo_root: Path,
    run_id: str | None = None,
    profile: str | None = None,
    ci_status_json: Path | None = None,
    readiness_evidence_file: Path | None = None,
    include_ignored_paths: list[str] | None = None,
    checkout_most_advanced_branch: bool = False,
    skill_review_report: AuditPayload | None = None,
    intent: AuditPayload | None = None,
    agent_review_mode: str | None = None,
    scan_exclusion_overlay: ScanExclusionOverlay | None = None,
    analysis_cache_root: Path | None = None,
    focus_paths: list[str] | None = None,
    analysis_mode: str = "full",
    cache_mode: CacheMode | str | None = None,
    cache_root: Path | None = None,
    performance_budget_seconds: float | None = None,
    progress: ProgressCallback | None = None,
    refresh_context: dict[str, object] | None = None,
) -> dict[str, Any]:
    resolved_run_id = generated_run_id() if run_id is None else run_id
    branch_warnings = prepare_scan_branch(
        repo_root, checkout_most_advanced_branch=checkout_most_advanced_branch
    )
    run_dir = prepare_artifact_dir(repo_root, resolved_run_id)
    analysis = analyze_read_only_audit(
        _audit_request(
            repo_root=repo_root,
            run_id=resolved_run_id,
            profile=profile,
            ci_status_json=ci_status_json,
            readiness_evidence_file=readiness_evidence_file,
            include_ignored_paths=include_ignored_paths,
            branch_warnings=branch_warnings,
            skill_review_report=skill_review_report,
            agent_review_mode=agent_review_mode,
            scan_exclusion_overlay=scan_exclusion_overlay,
            intent=intent,
            analysis_cache_root=analysis_cache_root,
            focus_paths=focus_paths,
            analysis_mode=analysis_mode,
            cache_mode=cache_mode,
            cache_root=cache_root,
            performance_budget_seconds=performance_budget_seconds,
        ),
        progress=progress,
    )
    _record_refresh_analysis(refresh_context, analysis, source="current-refresh-run")
    planned, artifact_paths = plan_and_write_run_v1_artifacts(analysis, run_dir=run_dir)
    skill_review = _skill_review_from_analysis(analysis, artifact_paths)

    return {
        "schema": "quality-runner-run-result-v0.1",
        "status": planned.status,
        "implementation_allowed": False,
        "run_id": resolved_run_id,
        "artifact_paths": artifact_paths,
        "module_status": _module_status_from_artifacts(artifact_paths),
        **_optional_field("skill_review", skill_review),
        "warnings": combined_warnings(
            _legacy_payload(analysis.scan), _legacy_payload(analysis.capability_map)
        ),
    }


def _audit_request(
    *,
    repo_root: Path,
    run_id: str,
    profile: str | None,
    ci_status_json: Path | None,
    readiness_evidence_file: Path | None,
    include_ignored_paths: list[str] | None,
    branch_warnings: list[dict[str, str]],
    skill_review_report: AuditPayload | None,
    agent_review_mode: str | None,
    scan_exclusion_overlay: ScanExclusionOverlay | None,
    intent: AuditPayload | None,
    analysis_cache_root: Path | None,
    focus_paths: list[str] | None,
    analysis_mode: str,
    cache_mode: CacheMode | str | None,
    cache_root: Path | None,
    performance_budget_seconds: float | None,
) -> AuditRequest:
    return AuditRequest(
        repo_root=repo_root,
        run_id=run_id,
        profile=profile,
        ci_status_json=ci_status_json,
        readiness_evidence_file=readiness_evidence_file,
        include_ignored_paths=tuple(include_ignored_paths or []),
        branch_warnings=tuple(_audit_warning(warning) for warning in branch_warnings),
        skill_review_report=skill_review_report,
        intent=intent,
        analysis_cache_root=analysis_cache_root,
        scan_exclusion_overlay=scan_exclusion_overlay,
        agent_review_mode=agent_review_mode,
        focus_paths=tuple(sorted(set(focus_paths or []))),
        analysis_mode=cast(
            AnalysisMode,
            analysis_mode if analysis_mode in {"balanced", "full"} else "full",
        ),
        cache_mode=cast(
            CacheMode | None,
            cache_mode if cache_mode in {"repo", "external", "disabled"} else None,
        ),
        cache_root=cache_root,
        performance_budget_seconds=performance_budget_seconds,
    )


def _audit_warning(warning: dict[str, str]) -> AuditWarning:
    return {
        "code": warning["code"],
        "message": warning["message"],
        "path": warning["path"],
    }


def _legacy_payload(payload: AuditPayload) -> dict[str, Any]:
    return cast(dict[str, Any], payload)


def _module_status_from_artifacts(artifact_paths: dict[str, str]) -> dict[str, Any]:
    path = artifact_paths.get("run_manifest_json")
    if not isinstance(path, str) or not path:
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    module_status = payload.get("module_status") if isinstance(payload, dict) else None
    return module_status if isinstance(module_status, dict) else {}


def _skill_review_from_analysis(
    analysis: Any,
    artifact_paths: dict[str, str],
) -> dict[str, Any] | None:
    return skill_review_summary(
        code_quality_scan=_legacy_payload(analysis.code_quality_scan),
        artifact_paths=artifact_paths,
        skill_review_report=(
            _legacy_payload(analysis.request.skill_review_report)
            if analysis.request.skill_review_report is not None
            else None
        ),
        agent_review_mode=_agent_review_mode(analysis),
    )


def _optional_field(key: str, value: object) -> dict[str, Any]:
    return {key: value} if value is not None else {}


def _agent_review_mode(analysis: Any) -> AgentReviewMode:
    mode = getattr(getattr(analysis, "request", None), "agent_review_mode", None)
    return cast(AgentReviewMode, mode) if mode in AGENT_REVIEW_MODES else "auto"


def _record_refresh_analysis(
    refresh_context: dict[str, object] | None,
    analysis: Any,
    *,
    source: str,
) -> None:
    if refresh_context is None:
        return
    refresh_context["audit_analysis"] = analysis
    refresh_context["analysis_source"] = source
