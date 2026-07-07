from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.fix_proposals import FIX_PROPOSE_RESULT_SCHEMA, propose_fix


def add_fix_proposal_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "propose-fix",
        help="Write structured fix proposals for a remediation finding group without applying changes",
    )
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument("--run-id", required=True, help="Existing Quality Runner run id")
    parser.add_argument(
        "--finding-group",
        required=True,
        help="Remediation slice id or handoff next-slice id to propose fixes for",
    )
    parser.add_argument("--proposal-id", default=None, help="Stable proposal id")
    parser.add_argument(
        "--finding-id",
        action="append",
        default=[],
        dest="finding_ids",
        help="Limit proposals to specific finding ids within the group",
    )
    parser.add_argument(
        "--actor",
        default="user",
        help="Actor recorded on the proposal artifact (default: user)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def propose_fix_command_payload(args: argparse.Namespace, *, repo_root: Path) -> dict[str, Any]:
    return propose_fix(
        repo_root=repo_root,
        run_id=args.run_id,
        finding_group=args.finding_group,
        proposal_id=args.proposal_id,
        finding_ids=args.finding_ids or None,
        actor=args.actor,
    )


FIX_PROPOSAL_RESULT_SCHEMAS = {FIX_PROPOSE_RESULT_SCHEMA}
