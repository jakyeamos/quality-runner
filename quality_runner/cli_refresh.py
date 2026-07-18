from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.cli_status import export_handoff_payload
from quality_runner.compatibility.legacy_workflow import refresh_payload
from quality_runner.core.audit_contracts import ScanExclusionOverlay
from quality_runner.exclusion_preflight import normalize_run_only_exclusion_overlay
from quality_runner.intent import resolve_workflow_intent
from quality_runner.phase_contract import load_phase_contract, scan_include_paths
from quality_runner.progress import ProgressCallback


def refresh_command_payload(
    args: argparse.Namespace,
    repo_root: Path,
    *,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    workflow_intent = resolve_workflow_intent(
        repo_root=repo_root,
        run_id=f"{args.run_id_prefix}-verify",
        goal=args.intent,
        intent_file=Path(args.intent_file).expanduser().resolve() if args.intent_file else None,
    )
    include_paths = tuple(getattr(args, "include_path", []) or [])
    if not include_paths and getattr(args, "phase_contract", None):
        contract = load_phase_contract(Path(args.phase_contract).expanduser().resolve())
        include_paths = scan_include_paths(contract)
    payload = refresh_payload(
        repo_root=repo_root,
        run_id_prefix=args.run_id_prefix,
        baseline_run_id=args.baseline_run_id,
        profile=args.profile,
        ci_status_json=Path(args.ci_status_json) if args.ci_status_json else None,
        readiness_evidence_file=(
            Path(args.readiness_evidence_file).expanduser().resolve()
            if args.readiness_evidence_file
            else None
        ),
        timeout_seconds=args.timeout_seconds,
        workflow_timeout_seconds=args.workflow_timeout_seconds,
        verify_timeout_seconds=args.verify_timeout_seconds,
        workflow_timeout_reason=args.workflow_timeout_reason,
        total_timeout_seconds=args.total_timeout_seconds,
        total_timeout_reason=args.total_timeout_reason,
        checkout_most_advanced_branch=args.checkout_most_advanced_branch,
        execute_discovered_gates=getattr(args, "execute_gates", False),
        allow_mutating_gates=args.allow_mutating_gates,
        worktree_mode=args.worktree_mode,
        allow_dirty_worktree_verify=args.allow_dirty_worktree_verify,
        intent=workflow_intent,
        review_cycle_id=args.review_cycle_id,
        review_iteration=args.review_iteration,
        agent_review_mode=getattr(args, "agent_review_mode", None),
        scan_exclusion_overlay=_scan_exclusion_overlay(args, repo_root),
        include_paths=include_paths,
        progress=progress,
    )
    if args.handoff_output:
        payload["handoff_export"] = export_handoff_payload(
            repo_root=repo_root,
            run_id=f"{args.run_id_prefix}-verify",
            output_path=Path(args.handoff_output).expanduser(),
        )
    return payload


def _scan_exclusion_overlay(
    args: argparse.Namespace,
    repo_root: Path,
) -> ScanExclusionOverlay | None:
    return normalize_run_only_exclusion_overlay(
        repo_root,
        getattr(args, "scan_exclusion", None),
        getattr(args, "scan_exclusion_module", None),
    )
