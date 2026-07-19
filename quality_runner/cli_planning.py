from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.delivery_contract import (
    preflight_delivery_contract,
    prepare_delivery_contract,
    reconcile_delivery_contract,
    refresh_delivery_contract,
)
from quality_runner.phase_automation import auto_plan
from quality_runner.phase_planning import (
    add_phase,
    close_phase,
    initialize_plan,
    next_plan,
    plan_phase,
    plan_status,
    record_batch,
    update_phase,
    verify_phase,
)


def add_planning_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    plan_parser = subparsers.add_parser("plan", help="Manage the QR-owned planning namespace")
    plan_subparsers = plan_parser.add_subparsers(dest="plan_action", required=True)

    plan_init = plan_subparsers.add_parser("init", help="Initialize QR planning files")
    plan_init.add_argument("repo_path", help="Target repository path")
    plan_init.add_argument("--json", action="store_true", help="Emit JSON output")

    plan_status_parser = plan_subparsers.add_parser("status", help="Show QR planning status")
    plan_status_parser.add_argument("repo_path", help="Target repository path")
    plan_status_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    plan_auto = plan_subparsers.add_parser(
        "auto",
        help="Automatically materialize security-first domain phases from a QR run",
    )
    plan_auto.add_argument("repo_path", help="Target repository path")
    source_group = plan_auto.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--run-id", help="QR run id containing a remediation plan")
    source_group.add_argument("--handoff-json", help="Agent handoff JSON path")
    plan_auto.add_argument("--json", action="store_true", help="Emit JSON output")

    contract_parser = plan_subparsers.add_parser(
        "contract", help="Prepare or refresh a QR delivery contract"
    )
    contract_subparsers = contract_parser.add_subparsers(
        dest="contract_action", required=True
    )
    for action, help_text in (
        ("prepare", "Create an immutable contract before research"),
        ("refresh", "Create a new immutable contract after research or context"),
    ):
        action_parser = contract_subparsers.add_parser(action, help=help_text)
        action_parser.add_argument("repo_path", help="Target repository path")
        action_parser.add_argument("--run-id", default=None, help="QR run id to bind to the contract")
        action_parser.add_argument("--phase-id", default=None)
        action_parser.add_argument("--plan-id", default=None)
        action_parser.add_argument("--intent", default=None)
        action_parser.add_argument(
            "--analysis-mode", choices=["balanced", "full"], default="balanced"
        )
        action_parser.add_argument(
            "--cache-mode", choices=["repo", "external", "disabled"], default="external"
        )
        action_parser.add_argument("--cache-dir", default=None)
        action_parser.add_argument("--performance-budget-seconds", type=float, default=30.0)
        action_parser.add_argument("--context-ref", action="append", default=[])
        action_parser.add_argument("--research-ref", action="append", default=[])
        if action == "refresh":
            action_parser.add_argument("--contract", required=True, help="Previous contract JSON")
        action_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    plan_preflight = plan_subparsers.add_parser(
        "preflight", help="Validate a native plan against an existing QR contract"
    )
    plan_preflight.add_argument("repo_path", help="Target repository path")
    plan_preflight.add_argument("--contract", required=True, help="Delivery contract JSON")
    plan_preflight.add_argument("--plan-file", required=True, help="Native plan JSON or Markdown")
    plan_preflight.add_argument("--json", action="store_true", help="Emit JSON output")

    plan_reconcile = plan_subparsers.add_parser(
        "reconcile", help="Reconcile structured execution evidence against a QR contract"
    )
    plan_reconcile.add_argument("repo_path", help="Target repository path")
    plan_reconcile.add_argument("--contract", required=True, help="Delivery contract JSON")
    plan_reconcile.add_argument("--result-file", required=True, help="Structured delivery result JSON")
    plan_reconcile.add_argument("--run-id", default=None, help="Current QR delta run id")
    plan_reconcile.add_argument("--json", action="store_true", help="Emit JSON output")

    phase_parser = subparsers.add_parser("phase", help="Manage QR-owned remediation phases")
    phase_subparsers = phase_parser.add_subparsers(dest="phase_action", required=True)

    phase_add = phase_subparsers.add_parser("add", help="Add a phase to the QR roadmap")
    phase_add.add_argument("repo_path", help="Target repository path")
    phase_add.add_argument("description", help="Phase goal or description")
    phase_add.add_argument("--json", action="store_true", help="Emit JSON output")

    phase_plan = phase_subparsers.add_parser(
        "plan", help="Generate QR-owned plans from a QR run or handoff"
    )
    phase_plan.add_argument("repo_path", help="Target repository path")
    phase_plan.add_argument("--phase", type=int, required=True, dest="phase_number")
    source_group = phase_plan.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--run-id", help="QR run id containing a remediation plan")
    source_group.add_argument("--handoff-json", help="Agent handoff JSON path")
    phase_plan.add_argument(
        "--candidate",
        default=None,
        dest="candidate_id",
        help="Plan one domain candidate instead of the full planning source",
    )
    phase_plan.add_argument("--json", action="store_true", help="Emit JSON output")

    phase_next = phase_subparsers.add_parser("next", help="Emit the next ready QR plan or wave")
    phase_next.add_argument("repo_path", help="Target repository path")
    phase_next.add_argument("--phase", type=int, default=None, dest="phase_number")
    phase_next.add_argument("--json", action="store_true", help="Emit JSON output")

    phase_record = phase_subparsers.add_parser(
        "record-batch", help="Record an external batch result"
    )
    phase_record.add_argument("repo_path", help="Target repository path")
    phase_record.add_argument("--phase", type=int, required=True, dest="phase_number")
    phase_record.add_argument("--plan", type=int, required=True, dest="plan_number")
    phase_record.add_argument("--result-file", required=True, help="Batch result JSON path")
    phase_record.add_argument("--json", action="store_true", help="Emit JSON output")

    phase_update = phase_subparsers.add_parser(
        "update", help="Apply a remediation-delta evidence update"
    )
    phase_update.add_argument("repo_path", help="Target repository path")
    phase_update.add_argument("--phase", type=int, required=True, dest="phase_number")
    phase_update.add_argument("--baseline-run-id", required=True)
    phase_update.add_argument("--run-id", required=True)
    phase_update.add_argument("--json", action="store_true", help="Emit JSON output")

    phase_verify = phase_subparsers.add_parser(
        "verify", help="Verify all QR-owned plans in a phase"
    )
    phase_verify.add_argument("repo_path", help="Target repository path")
    phase_verify.add_argument("--phase", type=int, required=True, dest="phase_number")
    phase_verify.add_argument("--run-id", required=True)
    phase_verify.add_argument("--json", action="store_true", help="Emit JSON output")

    phase_close = phase_subparsers.add_parser("close", help="Close a verified QR-owned phase")
    phase_close.add_argument("repo_path", help="Target repository path")
    phase_close.add_argument("--phase", type=int, required=True, dest="phase_number")
    phase_close.add_argument("--run-id", required=True)
    phase_close.add_argument("--json", action="store_true", help="Emit JSON output")


def planning_command_payload(args: argparse.Namespace, validated_repo_path: Any) -> dict[str, Any]:
    repo_root = validated_repo_path(args.repo_path)
    if args.command == "plan":
        if args.plan_action == "init":
            return initialize_plan(repo_root)
        if args.plan_action == "status":
            return plan_status(repo_root)
        if args.plan_action == "auto":
            return auto_plan(
                repo_root,
                run_id=args.run_id,
                handoff_json=(
                    Path(args.handoff_json).expanduser().resolve() if args.handoff_json else None
                ),
            )
        if args.plan_action == "contract":
            cache_root = (
                Path(args.cache_dir).expanduser().resolve()
                if args.cache_dir
                else None
            )
            common = {
                "repo_root": repo_root,
                "run_id": args.run_id,
                "phase_id": args.phase_id,
                "plan_id": args.plan_id,
                "intent": args.intent,
                "analysis_mode": args.analysis_mode,
                "cache_mode": args.cache_mode,
                "cache_root": cache_root,
                "performance_budget_seconds": args.performance_budget_seconds,
                "context_refs": args.context_ref,
                "research_refs": args.research_ref,
            }
            if args.contract_action == "prepare":
                return prepare_delivery_contract(**common)
            if args.contract_action == "refresh":
                return refresh_delivery_contract(
                    contract_path=Path(args.contract).expanduser().resolve(),
                    **common,
                )
        if args.plan_action == "preflight":
            return preflight_delivery_contract(
                repo_root,
                contract_path=Path(args.contract).expanduser().resolve(),
                plan_path=Path(args.plan_file).expanduser().resolve(),
            )
        if args.plan_action == "reconcile":
            return reconcile_delivery_contract(
                repo_root,
                contract_path=Path(args.contract).expanduser().resolve(),
                result_path=Path(args.result_file).expanduser().resolve(),
                run_id=args.run_id,
            )
    if args.command != "phase":
        raise ValueError(f"unsupported planning command: {args.command}")
    if args.phase_action == "add":
        return add_phase(repo_root, args.description)
    if args.phase_action == "plan":
        return plan_phase(
            repo_root,
            phase_number=args.phase_number,
            run_id=args.run_id,
            handoff_json=(
                Path(args.handoff_json).expanduser().resolve() if args.handoff_json else None
            ),
            candidate_id=args.candidate_id,
        )
    if args.phase_action == "next":
        return next_plan(repo_root, phase_number=args.phase_number)
    if args.phase_action == "record-batch":
        return record_batch(
            repo_root,
            phase_number=args.phase_number,
            plan_number=args.plan_number,
            result_file=Path(args.result_file).expanduser().resolve(),
        )
    if args.phase_action == "update":
        return update_phase(
            repo_root,
            phase_number=args.phase_number,
            baseline_run_id=args.baseline_run_id,
            run_id=args.run_id,
        )
    if args.phase_action == "verify":
        return verify_phase(repo_root, phase_number=args.phase_number, run_id=args.run_id)
    if args.phase_action == "close":
        return close_phase(repo_root, phase_number=args.phase_number, run_id=args.run_id)
    raise ValueError(f"unsupported phase command: {args.phase_action}")
