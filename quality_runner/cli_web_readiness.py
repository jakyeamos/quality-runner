from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Protocol

from quality_runner.config import load_repo_config
from quality_runner.web_readiness import (
    DEFAULT_REPORT_PATH,
    create_web_readiness_report,
    write_web_readiness_report,
)


class SubparserCollection(Protocol):
    def add_parser(self, name: str, **kwargs: Any) -> argparse.ArgumentParser: ...


def add_web_readiness_command(
    subparsers: SubparserCollection,
) -> None:
    parser = subparsers.add_parser(
        "web-readiness",
        help="Produce commit-bound source, artifact, and deployment web-readiness evidence",
    )
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument(
        "--deployment-evidence",
        default=None,
        help="Project-owned browser evidence using quality-runner-web-deployment-evidence/v1",
    )
    parser.add_argument(
        "--output",
        default=None,
        help=f"Report path (default: {DEFAULT_REPORT_PATH} inside the repository)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def web_readiness_command_payload(args: argparse.Namespace, *, repo_root: Path) -> dict[str, Any]:
    deployment_path = (
        Path(args.deployment_evidence).expanduser().resolve() if args.deployment_evidence else None
    )
    report = create_web_readiness_report(
        repo_root,
        config=load_repo_config(repo_root),
        deployment_evidence_path=deployment_path,
    )
    output = (
        Path(args.output).expanduser().resolve() if args.output else repo_root / DEFAULT_REPORT_PATH
    )
    report_path = write_web_readiness_report(report, output)
    return report | {"report_path": str(report_path)}
