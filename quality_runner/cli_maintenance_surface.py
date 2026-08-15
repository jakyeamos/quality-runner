from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from quality_runner.maintenance_surface import WORKTREE_REF, maintenance_surface_payload


def add_maintenance_surface_command(
    subparsers: Any,
) -> None:
    parser = subparsers.add_parser(
        "maintenance-surface",
        help="Describe a diff's maintenance surface without scoring line count",
    )
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument("--base", default="HEAD", help="Base Git revision (default: HEAD)")
    parser.add_argument(
        "--head",
        default=WORKTREE_REF,
        help="Head Git revision or WORKTREE (default: WORKTREE)",
    )
    parser.add_argument(
        "--behavior-added",
        action="append",
        default=[],
        help="Author-declared supported behavior added; repeat as needed",
    )
    parser.add_argument(
        "--behavior-removed",
        action="append",
        default=[],
        help="Author-declared supported behavior removed; repeat as needed",
    )
    parser.add_argument(
        "--consolidated-concept",
        action="append",
        default=[],
        help="Author-declared concept or owner consolidated; repeat as needed",
    )
    parser.add_argument(
        "--regression-proof",
        default=None,
        help="Optional quality-runner-regression-proof-v0.1 JSON",
    )
    parser.add_argument("--output", default=None, help="Write the JSON artifact to this path")
    parser.add_argument(
        "--handoff-output",
        default=None,
        help="Write a reviewer-facing Markdown summary to this path",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def maintenance_surface_command_payload(
    args: argparse.Namespace,
    *,
    validated_repo_path: Callable[[str], Path],
) -> dict[str, Any]:
    return maintenance_surface_payload(
        validated_repo_path(args.repo_path),
        base_ref=args.base,
        head_ref=args.head,
        behavior_added=tuple(args.behavior_added),
        behavior_removed=tuple(args.behavior_removed),
        consolidated_concepts=tuple(args.consolidated_concept),
        regression_proof_path=(
            Path(args.regression_proof).expanduser().resolve() if args.regression_proof else None
        ),
        output_path=Path(args.output) if args.output else None,
        handoff_output_path=Path(args.handoff_output) if args.handoff_output else None,
    )
