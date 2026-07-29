from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from quality_runner.application.audit_workflows import inspect_payload, run_payload
from quality_runner.application.outcome_projection import (
    LegacyPayload,
    project_audit_outcome,
    project_review_outcome,
    project_runs_outcome,
    project_verify_outcome,
)
from quality_runner.application.run_history import DEFAULT_HISTORY_LIMIT, load_run_history
from quality_runner.application.verification_workflows import verify_gates_payload
from quality_runner.artifacts import artifact_text_file
from quality_runner.core.audit_contracts import ScanExclusionOverlay
from quality_runner.core.outcome_contracts import JourneyOutcome
from quality_runner.git_branches import checked_out_branch


def audit_journey_outcome(
    *,
    repo_root: Path,
    run_id: str | None,
    profile: str | None,
    ci_status_json: Path | None,
    include_ignored_paths: list[str],
    checkout_most_advanced_branch: bool,
    skill_review_report: LegacyPayload | None,
    intent: LegacyPayload | None,
    inspect_only: bool,
    agent_review_mode: str | None = None,
    scan_exclusion_overlay: ScanExclusionOverlay | None = None,
    readiness_evidence_file: Path | None = None,
    include_paths: tuple[str, ...] = (),
) -> JourneyOutcome:
    branch_before = checked_out_branch(repo_root)
    payload = (
        inspect_payload(
            repo_root=repo_root,
            run_id=run_id,
            profile=profile,
            ci_status_json=ci_status_json,
            readiness_evidence_file=readiness_evidence_file,
            include_ignored_paths=include_ignored_paths,
            checkout_most_advanced_branch=checkout_most_advanced_branch,
            skill_review_report=skill_review_report,
            agent_review_mode=agent_review_mode,
            scan_exclusion_overlay=scan_exclusion_overlay,
            include_paths=include_paths,
            intent=intent,
        )
        if inspect_only
        else run_payload(
            repo_root=repo_root,
            run_id=run_id,
            profile=profile,
            ci_status_json=ci_status_json,
            readiness_evidence_file=readiness_evidence_file,
            include_ignored_paths=include_ignored_paths,
            checkout_most_advanced_branch=checkout_most_advanced_branch,
            skill_review_report=skill_review_report,
            agent_review_mode=agent_review_mode,
            scan_exclusion_overlay=scan_exclusion_overlay,
            include_paths=include_paths,
            intent=intent,
        )
    )
    return project_audit_outcome(
        _payload_mapping(payload),
        repo_root=repo_root,
        inspect_only=inspect_only,
        branch_switched=_branch_switched(branch_before, checked_out_branch(repo_root)),
    )


def verify_journey_outcome(
    *,
    repo_root: Path,
    run_id: str | None,
    profile: str | None,
    ci_status_json: Path | None,
    timeout_seconds: int,
    checkout_most_advanced_branch: bool,
    execute_discovered_gates: bool,
    read_only_gates: bool,
    allow_mutating_gates: bool,
    worktree_mode: str,
    allow_dirty_worktree_verify: bool,
    skill_review_report: LegacyPayload | None,
    intent: LegacyPayload | None,
    agent_review_mode: str | None = None,
    scan_exclusion_overlay: ScanExclusionOverlay | None = None,
    readiness_evidence_file: Path | None = None,
) -> JourneyOutcome:
    branch_before = checked_out_branch(repo_root)
    payload = verify_gates_payload(
        repo_root=repo_root,
        run_id=run_id,
        profile=profile,
        ci_status_json=ci_status_json,
        readiness_evidence_file=readiness_evidence_file,
        timeout_seconds=timeout_seconds,
        checkout_most_advanced_branch=checkout_most_advanced_branch,
        execute_discovered_gates=execute_discovered_gates,
        read_only_gates=read_only_gates,
        allow_mutating_gates=allow_mutating_gates,
        worktree_mode=worktree_mode,
        allow_dirty_worktree_verify=allow_dirty_worktree_verify,
        skill_review_report=skill_review_report,
        intent=intent,
        agent_review_mode=agent_review_mode,
        scan_exclusion_overlay=scan_exclusion_overlay,
    )
    legacy_payload = _payload_mapping(payload)
    return project_verify_outcome(
        legacy_payload,
        repo_root=repo_root,
        verification=_gate_verification(repo_root, legacy_payload),
        branch_switched=_branch_switched(branch_before, checked_out_branch(repo_root)),
    )


def review_journey_outcome(payload: LegacyPayload, *, repo_root: Path) -> JourneyOutcome:
    return project_review_outcome(payload, repo_root=repo_root)


def runs_journey_outcome(
    *,
    repo_root: Path,
    limit: int = DEFAULT_HISTORY_LIMIT,
    run_id: str | None = None,
) -> JourneyOutcome:
    return project_runs_outcome(
        load_run_history(repo_root=repo_root, limit=limit, run_id=run_id),
        repo_root=repo_root,
    )


def _gate_verification(repo_root: Path, payload: LegacyPayload) -> LegacyPayload | None:
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return None
    try:
        path = artifact_text_file(repo_root, run_id, "gate-verification.json")
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return None
    return _payload_mapping(loaded) if isinstance(loaded, dict) else None


def _payload_mapping(payload: Mapping[str, object]) -> LegacyPayload:
    return dict(payload)


def _branch_switched(before: str | None, after: str | None) -> bool:
    return before is not None and after is not None and before != after
