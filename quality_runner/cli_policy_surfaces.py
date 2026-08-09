from __future__ import annotations

import argparse
from typing import Any

from quality_runner.policy_surfaces import validate_policy_surfaces


def add_policy_surface_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "policy-surfaces",
        help="Validate policy artifacts with artifact-specific evidence",
    )
    commands = parser.add_subparsers(dest="policy_surfaces_command", required=True)
    check = commands.add_parser("check", help="Validate policy artifacts without source coverage")
    check.add_argument("repo_path", help="Target repository path")
    check.add_argument(
        "--changed-file",
        action="append",
        default=None,
        help="Limit validation to a changed path; repeat for multiple paths",
    )
    check.add_argument("--json", action="store_true", help="Emit JSON output")


def policy_surfaces_payload(args: argparse.Namespace, *, repo_path: Any) -> dict[str, Any]:
    if args.policy_surfaces_command != "check":
        raise ValueError("a policy-surfaces subcommand is required")
    return validate_policy_surfaces(repo_path(args.repo_path), paths=args.changed_file)
