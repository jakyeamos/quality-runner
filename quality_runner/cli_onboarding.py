from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from quality_runner.onboarding import onboarding_check_payload, write_onboarding_report

DEFAULT_MATRIX_PATH = Path.home() / ".agents" / "repository-onboarding-change-matrix.json"
DEFAULT_EVIDENCE_PATH = Path(".quality-runner/onboarding-evidence.json")


class SubparserCollection(Protocol):
    def add_parser(self, name: str, **kwargs: Any) -> argparse.ArgumentParser: ...


def add_onboarding_commands(
    subparsers: SubparserCollection,
) -> None:
    parser = subparsers.add_parser(
        "onboarding",
        help="Fail closed on incomplete or stale repository-onboarding evidence",
    )
    commands = parser.add_subparsers(dest="onboarding_command", required=True)
    check = commands.add_parser(
        "check",
        help="Validate a repository against the global onboarding matrix without changing it",
    )
    check.add_argument("repo_path", help="Target repository path")
    check.add_argument(
        "--matrix",
        default=str(DEFAULT_MATRIX_PATH),
        help="Fleet repository-onboarding change matrix",
    )
    check.add_argument(
        "--evidence",
        default=None,
        help="Exact-ref onboarding evidence envelope (defaults inside the target repository)",
    )
    check.add_argument(
        "--output",
        default=None,
        help="Explicit path for the machine-readable check receipt",
    )
    check.add_argument("--json", action="store_true", help="Emit JSON output")


def onboarding_command_payload(
    args: argparse.Namespace,
    *,
    validated_repo_path: Callable[[str], Path],
) -> dict[str, Any]:
    if args.onboarding_command != "check":
        raise ValueError("an onboarding subcommand is required")
    root = validated_repo_path(args.repo_path)
    evidence_path = (
        Path(args.evidence).expanduser().resolve()
        if isinstance(args.evidence, str) and args.evidence
        else root / DEFAULT_EVIDENCE_PATH
    )
    payload = onboarding_check_payload(
        repo_root=root,
        matrix_path=Path(args.matrix),
        evidence_path=evidence_path,
    )
    if isinstance(args.output, str) and args.output:
        write_onboarding_report(payload, Path(args.output))
    return payload
