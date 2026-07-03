from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.controller_reports import (
    build_controller_report_from_summary,
    lint_controller_report,
    normalize_controller_report,
)


def add_controller_report_summary_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--controller-report",
        action="store_true",
        help="Emit a strict controller-report skeleton instead of a run summary",
    )
    parser.add_argument("--branch-name", default=None, help="Branch name for --controller-report")
    parser.add_argument(
        "--thread-status",
        choices=sorted(("blocked", "complete", "ready-for-review")),
        default=None,
        help="Override inferred controller thread status for --controller-report",
    )
    parser.add_argument(
        "--blocker",
        action="append",
        default=[],
        help="Blocker to include in --controller-report; can be repeated",
    )
    parser.add_argument(
        "--file-changed",
        action="append",
        default=[],
        help="Changed file to include in --controller-report; can be repeated",
    )
    parser.add_argument("--commit-hash", default=None, help="Commit hash for --controller-report")
    parser.add_argument(
        "--push-status",
        default="not-pushed",
        help='Push status for --controller-report, for example "pushed" or "not-pushed"',
    )


def add_controller_report_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    controller_parser = subparsers.add_parser(
        "controller-report", help="Normalize or lint controller thread reports"
    )
    controller_subparsers = controller_parser.add_subparsers(dest="controller_report_command")
    normalize_parser = controller_subparsers.add_parser(
        "normalize", help="Normalize a worker report into the strict controller schema"
    )
    normalize_parser.add_argument("report_json", help="Worker report JSON path")
    normalize_parser.add_argument("--output", default=None, help="Write normalized report JSON to this path")
    normalize_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    lint_parser = controller_subparsers.add_parser(
        "lint", help="Lint a worker report after normalization"
    )
    lint_parser.add_argument("report_json", help="Worker report JSON path")
    lint_parser.add_argument(
        "--strict",
        action="store_true",
        help="Enforce completion semantics and repo-state concurrency guardrails",
    )
    lint_parser.add_argument("--json", action="store_true", help="Emit JSON output")


def controller_report_from_summary_payload(
    *,
    args: argparse.Namespace,
    repo_root: Path,
    summary: dict[str, Any],
) -> dict[str, Any]:
    return build_controller_report_from_summary(
        repo_path=str(repo_root),
        branch_name=args.branch_name or _git_branch(repo_root),
        summary=summary,
        baseline_run_id=args.baseline_run_id,
        git_status_short=_git_status_short(repo_root),
        files_changed=args.file_changed,
        blockers=args.blocker,
        commit_hash=args.commit_hash,
        push_status=args.push_status,
        status=args.thread_status,
    )


def controller_report_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.controller_report_command is None:
        raise ValueError("controller-report requires a subcommand")
    report = load_controller_report_json(Path(args.report_json))
    if args.controller_report_command == "normalize":
        normalized = normalize_controller_report(report)
        if args.output:
            output_path = Path(args.output).expanduser().resolve()
            output_path.write_text(
                json.dumps(normalized, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return normalized
    if args.controller_report_command == "lint":
        return lint_controller_report(report, strict=args.strict)
    raise ValueError(f"unsupported controller-report subcommand: {args.controller_report_command}")


def load_controller_report_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"controller report is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError("controller report JSON must contain an object")
    return payload


def _git_branch(repo_root: Path) -> str:
    return _git_command(repo_root, ["branch", "--show-current"]) or "unknown"


def _git_status_short(repo_root: Path) -> str:
    return _git_command(repo_root, ["status", "--short"])


def _git_command(repo_root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip()
