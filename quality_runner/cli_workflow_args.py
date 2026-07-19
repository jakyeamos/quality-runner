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
        "--readiness-evidence-file",
        default=None,
        help="Release-profile evidence JSON path inside the target repo",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt before excluding expensive default-ignored scan paths",
    )
    parser.add_argument(
        "--scan-exclusion",
        action="append",
        default=None,
        metavar="DIR",
        help=(
            "Exclude this repo-relative directory for this run only; repeat for multiple "
            "directories. This also changes security scan coverage."
        ),
    )
    parser.add_argument(
        "--scan-exclusion-module",
        action="append",
        default=None,
        metavar="MODULE=DIR",
        help=(
            "Exclude this repo-relative directory for one QR module only; use structural, "
            "code_quality, or security as MODULE and repeat the option as needed."
        ),
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
    parser.add_argument(
        "--agent-review-mode",
        choices=["off", "auto", "parallel", "required"],
        default=None,
        help="Agent skill-review policy for this run",
    )
    parser.add_argument(
        "--analysis-mode",
        choices=["balanced", "full"],
        default="full",
        help="Use the fast planning loop or the explicit full assurance scan",
    )
    parser.add_argument(
        "--cache-mode",
        choices=["repo", "external", "disabled"],
        default="repo",
        help="Choose repository, external, or disabled analysis-cache persistence",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="External cache root; used with --cache-mode external",
    )
    parser.add_argument(
        "--performance-budget-seconds",
        type=float,
        default=None,
        help="Record a bounded partial receipt when this analysis budget is exceeded",
    )
    add_intent_cli_arguments(parser)
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable stderr progress and heartbeat diagnostics",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def add_worktree_verify_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--worktree-mode",
        choices=["in-place", "disposable"],
        default="in-place",
        help="Use disposable with --execute-gates; in-place is retained for non-executing plans",
    )
    parser.add_argument(
        "--allow-dirty-worktree-verify",
        action="store_true",
        help="Allow disposable verification when the source worktree has local edits",
    )


def add_verify_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Per-gate command timeout",
    )
    parser.add_argument(
        "--read-only-gates",
        action="store_true",
        help="Skip gates that are known or likely to mutate source files",
    )
    parser.add_argument(
        "--execute-gates",
        action="store_true",
        help="Execute discovered repository commands in a disposable worktree",
    )
    parser.add_argument(
        "--allow-mutating-gates",
        action="store_true",
        help="Allow known or suspected mutating gates to execute",
    )
    add_worktree_verify_arguments(parser)
