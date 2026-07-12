from __future__ import annotations

import argparse

from quality_runner.application.run_history import DEFAULT_HISTORY_LIMIT
from quality_runner.cli_workflow_args import add_verify_arguments, add_workflow_arguments


def add_journey_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    audit_parser = subparsers.add_parser(
        "audit",
        help="Inspect a repository and prepare its remediation outcome",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "By default, audit prepares a remediation plan. Use --inspect-only for a\n"
            "discovery-only pass. Both modes write Quality Runner evidence artifacts\n"
            "but do not edit source files."
        ),
    )
    add_workflow_arguments(audit_parser)
    audit_parser.add_argument(
        "--inspect-only",
        action="store_true",
        help="Inspect repository evidence without preparing a remediation plan",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify configured quality gates with explicit execution consent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Default verification records command evidence only. To run discovered commands,\n"
            "pass --execute-gates --worktree-mode disposable. Disposable execution protects\n"
            "the source worktree from ordinary mutations, but it is not a host sandbox."
        ),
    )
    add_workflow_arguments(verify_parser)
    add_verify_arguments(verify_parser)

    runs_parser = subparsers.add_parser(
        "runs",
        help="Read recent Quality Runner evidence without writing new artifacts",
    )
    runs_parser.add_argument("repo_path", help="Target repository path")
    runs_parser.add_argument("--run-id", default=None, help="Show one specific run")
    runs_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_HISTORY_LIMIT,
        help=f"Maximum recent runs to show (default: {DEFAULT_HISTORY_LIMIT})",
    )
    runs_parser.add_argument("--json", action="store_true", help="Emit JSON output")
