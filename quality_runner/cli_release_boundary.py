from __future__ import annotations

import argparse
from typing import Any

from quality_runner.release_boundary import release_boundary_payload


def add_release_boundary_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "release-boundary",
        help="Validate public release classification, archives, fixtures, and clean-room install",
    )
    parser.add_argument("repo_path", help="Repository checkout being prepared for release")
    parser.add_argument(
        "--dist-dir", required=True, help="Directory containing one wheel and sdist"
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def release_boundary_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    from pathlib import Path

    return release_boundary_payload(
        repo_root=Path(args.repo_path),
        dist_dir=Path(args.dist_dir),
        run_clean_room=True,
    )
