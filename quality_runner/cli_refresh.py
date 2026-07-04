from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.cli_status import export_handoff_payload
from quality_runner.workflow import refresh_payload


def refresh_command_payload(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    payload = refresh_payload(
        repo_root=repo_root,
        run_id_prefix=args.run_id_prefix,
        baseline_run_id=args.baseline_run_id,
        profile=args.profile,
        ci_status_json=Path(args.ci_status_json) if args.ci_status_json else None,
        timeout_seconds=args.timeout_seconds,
        workflow_timeout_seconds=args.workflow_timeout_seconds,
        verify_timeout_seconds=args.verify_timeout_seconds,
        workflow_timeout_reason=args.workflow_timeout_reason,
        total_timeout_seconds=args.total_timeout_seconds,
        total_timeout_reason=args.total_timeout_reason,
        checkout_most_advanced_branch=args.checkout_most_advanced_branch,
        allow_mutating_gates=args.allow_mutating_gates,
    )
    if args.handoff_output:
        payload["handoff_export"] = export_handoff_payload(
            repo_root=repo_root,
            run_id=f"{args.run_id_prefix}-verify",
            output_path=Path(args.handoff_output).expanduser().resolve(),
        )
    return payload
