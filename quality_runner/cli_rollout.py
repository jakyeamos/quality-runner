from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.rollout import rollout_payload


def add_rollout_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    rollout_parser = subparsers.add_parser(
        "rollout",
        help="Run safe refreshes across a repo list and collect controller reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Repo list formats:\n"
            "  text: /path/to/repo [baseline-run-id] [name]\n"
            "  csv:  /path/to/repo,baseline-run-id,name\n"
            '  json: ["/path/to/repo", {"repo_path": "/path", "baseline_run_id": "..."}]\n\n'
            "Rollout runs repos sequentially, uses read-only refresh gates by default, and writes\n"
            "rollout-ledger.json plus one controller-report JSON per repo under --output-dir."
        ),
    )
    rollout_parser.add_argument(
        "repo_list",
        nargs="?",
        help="Text or JSON repo list. Also accepts repeated --repo entries.",
    )
    rollout_parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="Repo path to include without a repo-list file; can be repeated",
    )
    rollout_parser.add_argument(
        "--run-id-prefix",
        default=None,
        help="Prefix used for rollout and per-repo refresh run ids",
    )
    rollout_parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for rollout-ledger.json and controller reports",
    )
    rollout_parser.add_argument("--profile", default=None, help="Standards profile override")
    rollout_parser.add_argument(
        "--ci-status-json",
        default=None,
        help="Local CI status JSON export to attach to every repo refresh",
    )
    rollout_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Per-gate command timeout for each refresh",
    )
    rollout_parser.add_argument(
        "--workflow-timeout-seconds",
        type=int,
        default=None,
        help="Backward-compatible alias for --verify-timeout-seconds",
    )
    rollout_parser.add_argument(
        "--verify-timeout-seconds",
        type=int,
        default=None,
        help="Verify-gates phase timeout for each refresh",
    )
    rollout_parser.add_argument(
        "--workflow-timeout-reason",
        default=None,
        help="Reason recorded when a repo verify-phase timeout fires",
    )
    rollout_parser.add_argument(
        "--total-timeout-seconds",
        type=int,
        default=None,
        help="Optional hard deadline for each full repo refresh",
    )
    rollout_parser.add_argument(
        "--total-timeout-reason",
        default=None,
        help="Reason recorded when a repo total refresh timeout fires",
    )
    rollout_parser.add_argument(
        "--checkout-most-advanced-branch",
        action="store_true",
        help="Switch each repo to the local branch with the highest commit count before scanning",
    )
    rollout_parser.add_argument(
        "--allow-mutating-gates",
        action="store_true",
        help="Allow known or suspected mutating gates during each refresh",
    )
    rollout_parser.add_argument("--json", action="store_true", help="Emit JSON output")


def rollout_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    return rollout_payload(
        repo_list_path=Path(args.repo_list) if args.repo_list else None,
        repos=args.repo,
        run_id_prefix=args.run_id_prefix,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        profile=args.profile,
        ci_status_json=Path(args.ci_status_json) if args.ci_status_json else None,
        timeout_seconds=args.timeout_seconds,
        workflow_timeout_seconds=args.workflow_timeout_seconds,
        verify_timeout_seconds=args.verify_timeout_seconds,
        workflow_timeout_reason=args.workflow_timeout_reason,
        total_timeout_seconds=args.total_timeout_seconds,
        total_timeout_reason=args.total_timeout_reason,
        checkout_most_advanced_branch=args.checkout_most_advanced_branch,
        allow_mutating_gates=args.allow_mutating_gates,
    )
