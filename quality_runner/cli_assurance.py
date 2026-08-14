from __future__ import annotations

import argparse
from typing import Any

from quality_runner.cli_behavior import behavior_command_payload
from quality_runner.cli_fleet import fleet_command_payload


def assurance_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "behavior":
        return behavior_command_payload(args)
    if args.command == "fleet":
        return fleet_command_payload(args)
    raise ValueError(f"unsupported assurance command: {args.command}")
