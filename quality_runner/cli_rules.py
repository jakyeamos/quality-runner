from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.rule_registry import rule_registry


def add_rule_commands(subparsers: Any) -> None:
    rules = subparsers.add_parser(
        "rules", help="Inspect the canonical Quality Runner rule registry"
    )
    actions = rules.add_subparsers(dest="rules_action", required=True)
    registry = actions.add_parser(
        "registry", help="Report exact rules, dynamic families, verification, and promotion"
    )
    registry.add_argument("repo_path", nargs="?", default=".")
    registry.add_argument("--json", action="store_true")


def rule_command_payload(args: Any) -> dict[str, Any]:
    if args.command != "rules" or args.rules_action != "registry":
        raise ValueError("unsupported rules command")
    return rule_registry(Path(args.repo_path))
