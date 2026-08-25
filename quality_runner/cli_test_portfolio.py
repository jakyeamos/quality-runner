"""CLI routing for test-portfolio review and removal-proof evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.test_portfolio import (
    audit_test_portfolio,
    build_test_removal_proof,
    load_test_portfolio_json,
    write_test_portfolio_json,
)


def add_test_portfolio_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "tests",
        help="Review test value and validate exact-revision removal evidence",
    )
    actions = parser.add_subparsers(dest="tests_action", required=True)
    for action, help_text in (
        ("portfolio-audit", "Classify caller-assembled test value evidence"),
        ("removal-proof", "Fail closed on test-removal evidence gaps"),
    ):
        action_parser = actions.add_parser(action, help=help_text)
        action_parser.add_argument("manifest_path", help="Input manifest JSON")
        action_parser.add_argument("--output", default=None, help="Write artifact JSON")
        action_parser.add_argument("--json", action="store_true", help="Emit JSON output")


def test_portfolio_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    manifest_path = Path(args.manifest_path).expanduser().resolve()
    manifest = load_test_portfolio_json(manifest_path)
    if args.tests_action == "portfolio-audit":
        artifact = audit_test_portfolio(manifest)
    elif args.tests_action == "removal-proof":
        artifact = build_test_removal_proof(manifest)
    else:
        raise ValueError(f"unsupported tests action: {args.tests_action}")
    output_path = write_test_portfolio_json(Path(args.output), artifact) if args.output else None
    return {
        **artifact,
        "operation": args.tests_action,
        "input_path": str(manifest_path),
        "output_path": str(output_path) if output_path else None,
    }
