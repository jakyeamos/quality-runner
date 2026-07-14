from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

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
    plan_parser = subparsers.add_parser(
        "plan", help="Manage the QR-owned planning namespace"
    )
    plan_subparsers = plan_parser.add_subparsers(dest="plan_action", required=True)

    plan_init = plan_subparsers.add_parser("init", help="Initialize QR planning files")
    plan_init.add_argument("repo_path", help="Target repository path")
    plan_init.add_argument("--json", action="store_true", help="Emit JSON output")

    plan_status_parser = plan_subparsers.add_parser(
        "status", help="Show QR planning status"
    )
    plan_status_parser.add_argument("repo_path", help="Target repository path")
    plan_status_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    phase_parser = subparsers.add_parser(
        "phase", help="Manage QR-owned remediation phases"
    )
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
    phase_plan.add_argument("--json", action="store_true", help="Emit JSON output")

    phase_next = phase_subparsers.add_parser(
        "next", help="Emit the next ready QR plan or wave"
    )
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

    phase_close = phase_subparsers.add_parser(
        "close", help="Close a verified QR-owned phase"
    )
    phase_close.add_argument("repo_path", help="Target repository path")
    phase_close.add_argument("--phase", type=int, required=True, dest="phase_number")
    phase_close.add_argument("--run-id", required=True)
    phase_close.add_argument("--json", action="store_true", help="Emit JSON output")


def planning_command_payload(
    args: argparse.Namespace, validated_repo_path: Any
) -> dict[str, Any]:
    repo_root = validated_repo_path(args.repo_path)
    if args.command == "plan":
        if args.plan_action == "init":
            return initialize_plan(repo_root)
        if args.plan_action == "status":
            return plan_status(repo_root)
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
                Path(args.handoff_json).expanduser().resolve()
                if args.handoff_json
                else None
            ),
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
