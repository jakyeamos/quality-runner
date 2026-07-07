from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.gate_controller import (
    GATE_RESPOND_RESULT_SCHEMA,
    GATE_RUN_RESULT_SCHEMA,
    GATE_STATUS_RESULT_SCHEMA,
    create_gate_run,
    gate_status_payload,
    record_gate_response,
)


def add_gate_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    gate_parser = subparsers.add_parser(
        "gate",
        help="Create a driveable gate run from an existing Quality Runner run",
    )
    gate_parser.add_argument("repo_path", help="Target repository path")
    gate_parser.add_argument("--run-id", required=True, help="Existing Quality Runner run id")
    gate_parser.add_argument("--gate-run-id", default=None, help="Stable gate run id")
    gate_parser.add_argument(
        "--intent",
        default=None,
        help="Author intent goal when the source run has no intent artifact",
    )
    gate_parser.add_argument(
        "--intent-file",
        default=None,
        help="Intent JSON inside the target repo when the source run has no intent artifact",
    )
    gate_parser.add_argument(
        "--actor",
        default="user",
        help="Actor recorded on gate responses (default: user)",
    )
    gate_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    gate_status_parser = subparsers.add_parser(
        "gate-status",
        help="Read an in-flight gate run and response history",
    )
    gate_status_parser.add_argument("repo_path", help="Target repository path")
    gate_status_parser.add_argument("--gate-run-id", required=True, help="Gate run id")
    gate_status_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    gate_respond_parser = subparsers.add_parser(
        "gate-respond",
        help="Record a controller decision for an in-flight gate run",
    )
    gate_respond_parser.add_argument("repo_path", help="Target repository path")
    gate_respond_parser.add_argument("--gate-run-id", required=True, help="Gate run id")
    gate_respond_parser.add_argument(
        "--action",
        required=True,
        choices=[
            "approve",
            "fix",
            "skip",
            "route-next-slice",
            "record-disposition",
            "abort",
        ],
        help="Controller action to record",
    )
    gate_respond_parser.add_argument(
        "--finding-id",
        action="append",
        default=[],
        dest="finding_ids",
        help="Finding ids targeted by this response",
    )
    gate_respond_parser.add_argument("--notes", default=None, help="Optional response notes")
    gate_respond_parser.add_argument(
        "--disposition",
        default=None,
        choices=sorted(
            {
                "accepted-intentional",
                "accepted-false-positive",
                "blocked-with-prerequisite",
            }
        ),
        help="Disposition status for record-disposition",
    )
    gate_respond_parser.add_argument(
        "--owner",
        default=None,
        help="Owner recorded for record-disposition (defaults to --actor)",
    )
    gate_respond_parser.add_argument(
        "--actor",
        default="user",
        help="Actor recorded on the response (default: user)",
    )
    gate_respond_parser.add_argument("--json", action="store_true", help="Emit JSON output")


def gate_command_payload(args: argparse.Namespace, *, repo_root: Path) -> dict[str, Any]:
    return create_gate_run(
        repo_root=repo_root,
        run_id=args.run_id,
        gate_run_id=args.gate_run_id,
        goal=args.intent,
        intent_file=Path(args.intent_file).expanduser().resolve() if args.intent_file else None,
        actor=args.actor,
    )


def gate_status_command_payload(args: argparse.Namespace, *, repo_root: Path) -> dict[str, Any]:
    return gate_status_payload(repo_root=repo_root, gate_run_id=args.gate_run_id)


def gate_respond_command_payload(args: argparse.Namespace, *, repo_root: Path) -> dict[str, Any]:
    return record_gate_response(
        repo_root=repo_root,
        gate_run_id=args.gate_run_id,
        action=args.action,
        actor=args.actor,
        finding_ids=args.finding_ids,
        notes=args.notes,
        disposition=args.disposition,
        owner=args.owner,
    )


GATE_RESULT_SCHEMAS = {
    GATE_RUN_RESULT_SCHEMA,
    GATE_STATUS_RESULT_SCHEMA,
    GATE_RESPOND_RESULT_SCHEMA,
}
