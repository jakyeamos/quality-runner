from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.remediation_delta import (
    build_remediation_delta,
    persist_remediation_delta,
)


def add_remediation_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "remediation-delta",
        help="Compare two QR runs for tool-neutral remediation updates",
    )
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument("--run-id", required=True, help="Current QR run id")
    parser.add_argument("--baseline-run-id", required=True, help="Earlier QR run id")
    parser.add_argument("--output", default=None, help="Also write Markdown to this path")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def remediation_delta_command_payload(
    args: argparse.Namespace, repo_root: Path
) -> dict[str, Any]:
    payload = build_remediation_delta(
        repo_root=repo_root,
        current_run_id=args.run_id,
        baseline_run_id=args.baseline_run_id,
    )
    paths = persist_remediation_delta(
        repo_root=repo_root,
        current_run_id=args.run_id,
        payload=payload,
    )
    payload["artifact_paths"] = paths
    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            Path(paths["remediation_delta_md"]).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        payload["output_path"] = str(output_path)
    return payload
