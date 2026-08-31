from __future__ import annotations

import argparse
from typing import Any, Protocol

from quality_runner.release_boundary import (
    DEFAULT_REPORT_PATH,
    release_boundary_payload,
    write_release_boundary_report,
)


class SubparserCollection(Protocol):
    def add_parser(self, name: str, **kwargs: Any) -> argparse.ArgumentParser: ...


def add_release_boundary_command(
    subparsers: SubparserCollection,
) -> None:
    parser = subparsers.add_parser(
        "release-boundary",
        help="Validate public release classification, archives, fixtures, and clean-room install",
    )
    parser.add_argument("repo_path", help="Repository checkout being prepared for release")
    parser.add_argument(
        "--dist-dir", required=True, help="Directory containing one wheel and sdist"
    )
    parser.add_argument(
        "--output",
        default=None,
        help=f"Receipt path (default: {DEFAULT_REPORT_PATH} inside the repository)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def release_boundary_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    from pathlib import Path

    repo_root = Path(args.repo_path).expanduser().resolve()
    report = release_boundary_payload(
        repo_root=repo_root,
        dist_dir=Path(args.dist_dir),
        run_clean_room=True,
    )
    output = (
        Path(args.output).expanduser().resolve() if args.output else repo_root / DEFAULT_REPORT_PATH
    )
    report_path = write_release_boundary_report(report, output)
    try:
        display_path = report_path.relative_to(repo_root).as_posix()
    except ValueError:
        display_path = report_path.name
    return report | {"report_path": display_path}
