from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.phase_closure import phase_closure_payload
from quality_runner.phase_contract import load_phase_contract


def add_phase_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "phase-check",
        help="Evaluate a GSD phase contract against two QR runs",
    )
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument("--run-id", required=True, help="Current QR run id")
    parser.add_argument("--baseline-run-id", required=True, help="Baseline QR run id")
    parser.add_argument("--contract", required=True, help="Phase contract JSON path")
    parser.add_argument(
        "--changed-path",
        action="append",
        default=[],
        help="Changed path to evaluate against early-refresh triggers; repeat as needed",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def phase_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_path).expanduser().resolve()
    contract = load_phase_contract(Path(args.contract).expanduser().resolve())
    return phase_closure_payload(
        repo_root=repo_root,
        current_run_id=args.run_id,
        baseline_run_id=args.baseline_run_id,
        contract=contract,
        changed_paths=args.changed_path,
    )
