from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.behavior_receipts import record_edge_trace, verify_behavior_command
from quality_runner.fleet.behavior_contract import EDGE_ENVIRONMENTS, EDGE_SURFACES


def add_behavior_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "behavior", help="Run declared behavior validators and write immutable receipts"
    )
    actions = parser.add_subparsers(dest="behavior_action", required=True)
    verify = actions.add_parser(
        "verify", help="Run one bounded validator and seal its scenario results"
    )
    verify.add_argument("repo_path", help="Repository checkout containing the behavior contract")
    verify.add_argument("--behavior-id", required=True, help="Behavior id covered by the command")
    verify.add_argument(
        "--scenario-id",
        action="append",
        default=[],
        help="Scenario id covered by the command; repeat or omit to cover the behavior's scenarios",
    )
    verify.add_argument(
        "--timeout-seconds", type=int, default=120, help="Bounded validator timeout"
    )
    verify.add_argument("--json", action="store_true", help="Emit JSON output")
    verify.add_argument(
        "validator_command",
        nargs=argparse.REMAINDER,
        help="Validator argv after --; no shell interpolation is performed",
    )
    record = actions.add_parser(
        "record-edge",
        help="Validate a bounded hostile-session trace and seal direct-surface evidence",
    )
    record.add_argument("--repo", required=True, help="Repository checkout")
    record.add_argument("--behavior", required=True, help="Behavior id")
    record.add_argument("--scenario", required=True, help="Scenario id")
    record.add_argument("--environment", required=True, choices=sorted(EDGE_ENVIRONMENTS))
    record.add_argument("--surface", required=True, choices=sorted(EDGE_SURFACES))
    record.add_argument("--status", required=True, choices=["passed", "failed", "blocked"])
    record.add_argument("--trace", required=True, type=Path, help="Edge trace JSON")
    record.add_argument("--json", action="store_true", help="Emit JSON output")


def behavior_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.behavior_action == "verify":
        return verify_behavior_command(
            repo_root=Path(args.repo_path),
            behavior_id=args.behavior_id,
            scenario_ids=args.scenario_id,
            command=args.validator_command,
            timeout_seconds=args.timeout_seconds,
        )
    if args.behavior_action == "record-edge":
        return record_edge_trace(
            repo_root=Path(args.repo),
            behavior_id=args.behavior,
            scenario_id=args.scenario,
            environment=args.environment,
            surface=args.surface,
            status=args.status,
            trace_path=args.trace,
        )
    raise ValueError(f"unsupported behavior action: {args.behavior_action}")
