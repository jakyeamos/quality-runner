from __future__ import annotations

import argparse
from typing import Any

from quality_runner.repo_hygiene import apply_confirmed_ignore_rules, check_repo_hygiene


def add_repo_hygiene_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "repo-hygiene",
        help="Check tracked generated output, package-manager policy, and CI coverage",
    )
    commands = parser.add_subparsers(dest="repo_hygiene_command")

    check_parser = commands.add_parser(
        "check",
        help="Run the read-only repo-hygiene-v1 gate",
    )
    check_parser.add_argument("repo_path", help="Target repository path")
    check_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    apply_parser = commands.add_parser(
        "apply",
        help="Preview or append confirmed generated-output ignore rules",
    )
    apply_parser.add_argument("repo_path", help="Target repository path")
    apply_parser.add_argument(
        "--apply",
        action="store_true",
        help="Write confirmed rules; ownership-blocked worktrees are never changed",
    )
    apply_parser.add_argument("--json", action="store_true", help="Emit JSON output")


def repo_hygiene_payload(args: argparse.Namespace, *, validated_repo_path: Any) -> dict[str, Any]:
    repo_path = validated_repo_path(args.repo_path)
    if args.repo_hygiene_command == "check":
        return check_repo_hygiene(repo_path)
    if args.repo_hygiene_command == "apply":
        return apply_confirmed_ignore_rules(repo_path, apply=bool(args.apply))
    raise ValueError("a repo-hygiene subcommand is required")
