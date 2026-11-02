from __future__ import annotations

import argparse
from typing import Any


def add_dogfood_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "dogfood",
        help="Inspect local task-workflow telemetry or serve the Codex lifecycle hook",
    )
    actions = parser.add_subparsers(dest="dogfood_action", required=True)

    report = actions.add_parser("report", help="Summarize privacy-bounded local dogfood events")
    report.add_argument("--state-dir", default=None, help=argparse.SUPPRESS)
    report.add_argument("--json", action="store_true", help="Emit canonical JSON output")

    hook = actions.add_parser("codex-hook", help="Process one Codex lifecycle hook payload")
    hook.add_argument("--state-dir", default=None, help=argparse.SUPPRESS)
    hook.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
