from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from quality_runner.artifacts import write_json
from quality_runner.ci_gate_audit import audit_ci_gate_candidates
from quality_runner.fleet.contracts import parse_as_of


class SubparserCollection(Protocol):
    def add_parser(self, name: str, **kwargs: Any) -> argparse.ArgumentParser: ...


def add_ci_gate_audit_command(
    subparsers: SubparserCollection,
) -> None:
    parser = subparsers.add_parser(
        "ci-gate-audit",
        help="Recommend evidence-backed repository-specific CI gates without making them required",
    )
    parser.add_argument("repo_path", help="Repository to inspect")
    parser.add_argument("--as-of", default=None, help="Stable ISO-8601 audit timestamp")
    parser.add_argument("--output", default=None, help="Optional JSON artifact path")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def ci_gate_audit_command_payload(
    args: argparse.Namespace,
    *,
    validated_repo_path: Callable[[str], Path],
) -> dict[str, Any]:
    report = audit_ci_gate_candidates(
        validated_repo_path(args.repo_path), generated_at=parse_as_of(args.as_of)
    )
    if args.output:
        output = Path(args.output).expanduser().resolve()
        write_json(output, report)
        return {**report, "report_path": str(output)}
    return report
