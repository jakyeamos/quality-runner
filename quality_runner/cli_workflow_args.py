from __future__ import annotations

import argparse

from quality_runner.intent import add_intent_cli_arguments


def add_workflow_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument("--run-id", default=None, help="Stable run id")
    parser.add_argument("--profile", default=None, help="Standards profile override")
    parser.add_argument(
        "--ci-status-json",
        default=None,
        help="Local CI status JSON export to attach to capability evidence",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt before excluding expensive default-ignored scan paths",
    )
    parser.add_argument(
        "--checkout-most-advanced-branch",
        action="store_true",
        help="Switch to the local branch with the highest commit count before scanning",
    )
    parser.add_argument(
        "--skill-review-report",
        default=None,
        help="Validated agent skill review report JSON to merge into findings",
    )
    add_intent_cli_arguments(parser)
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def add_worktree_verify_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--worktree-mode",
        choices=["in-place", "disposable"],
        default="in-place",
        help="Run gate commands in-place or inside a disposable git worktree at HEAD",
    )
    parser.add_argument(
        "--allow-dirty-worktree-verify",
        action="store_true",
        help="Allow disposable verification when the source worktree has local edits",
    )
