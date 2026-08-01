from __future__ import annotations

import argparse


def add_task_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    task_parser = subparsers.add_parser(
        "task",
        help="Capture and enforce a task-scoped preventative quality baseline",
    )
    actions = task_parser.add_subparsers(dest="task_action", required=True)

    start = actions.add_parser("start", help="Capture the pre-edit task baseline")
    _common_arguments(start)
    start.add_argument(
        "--baseline-ref",
        default=None,
        help="Immutable Git revision to scan instead of the current workspace",
    )
    start.add_argument(
        "--intent",
        default=None,
        help="Optional task-intent file whose digest is recorded with the baseline",
    )

    check = actions.add_parser(
        "check",
        help="Run the authoritative completion check for the exact current workspace",
    )
    _common_arguments(check)

    rebaseline = actions.add_parser(
        "rebaseline",
        help="Capture a new baseline while preserving task lineage",
    )
    _common_arguments(rebaseline)
    rebaseline.add_argument("--reason", required=True, help="Why a new baseline is required")


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument("--task-id", required=True, help="Stable task identifier")
    parser.add_argument("--json", action="store_true", help="Emit canonical JSON output")
