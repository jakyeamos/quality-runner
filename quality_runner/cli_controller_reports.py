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
    validate_controller_report,
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
    parser.add_argument(
        "--commit-hash",
        default=None,
        help="Commit created by this task for --controller-report",
    )
    parser.add_argument(
        "--target-head",
        default=None,
        help="Target repo HEAD SHA for --controller-report; defaults to current HEAD",
    )
    parser.add_argument(
        "--pre-head",
        default=None,
        help="Target repo HEAD before the worker task started",
    )
    parser.add_argument(
        "--pre-git-status-short",
        default=None,
        help="Target repo git status --short output before the worker task started",
    )
    parser.add_argument(
        "--concurrency-note",
        default=None,
        help="Explanation for target HEAD changes observed during the worker task",
    )
    parser.add_argument(
        "--push-status",
        default="not-pushed",
        help='Push status for --controller-report, for example "pushed" or "not-pushed"',
    )
    parser.add_argument("--report-output", default=None, help="Write controller report JSON to this path")
    parser.add_argument(
        "--lint-report",
        action="store_true",
        help="Run strict controller-report lint on the generated report",
    )
    parser.add_argument(
        "--validate-report",
        action="store_true",
        help="Run validate-report semantics on the generated report",
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
    output_path = Path(args.report_output).expanduser().resolve() if args.report_output else None
    target_head = args.target_head or _git_head(repo_root)
    payload = build_controller_report_from_summary(
        repo_path=str(repo_root),
        branch_name=args.branch_name or _git_branch(repo_root),
        summary=summary,
        baseline_run_id=args.baseline_run_id,
        git_status_short=_git_status_short(repo_root),
        files_changed=args.file_changed,
        blockers=args.blocker or None,
        commit_hash=args.commit_hash,
        target_head=target_head,
        commit_created_by_task=bool(args.commit_hash),
        push_status=args.push_status,
        status=args.thread_status,
        pre_head=args.pre_head,
        pre_git_status_short=args.pre_git_status_short,
        concurrency_note=args.concurrency_note,
        report_path=str(output_path) if output_path else None,
        generation_command=_summary_generation_command(args=args, repo_root=repo_root),
    )
    self_checks: list[dict[str, Any]] = []
    if output_path:
        _write_json(output_path, payload)
    if args.lint_report:
        lint_result = lint_controller_report(payload, strict=True)
        self_checks.append(
            {
                "command": _lint_command(output_path),
                "status": lint_result["status"],
                "errors": lint_result["errors"],
            }
        )
    if args.validate_report:
        validation = validate_controller_report(payload)
        self_checks.append(
            {
                "command": _validate_command(output_path),
                "status": validation["status"],
                "errors": validation["errors"],
            }
        )
    if self_checks:
        payload["self_checks"] = self_checks
        if output_path:
            _write_json(output_path, payload)
    return payload


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


def has_rejected_self_check(payload: dict[str, Any]) -> bool:
    checks = payload.get("self_checks")
    return isinstance(checks, list) and any(
        isinstance(check, dict) and check.get("status") == "rejected" for check in checks
    )


def _git_branch(repo_root: Path) -> str:
    return _git_command(repo_root, ["branch", "--show-current"]) or "unknown"


def _git_status_short(repo_root: Path) -> str:
    return _git_command(repo_root, ["status", "--short"])


def _git_head(repo_root: Path) -> str:
    return _git_command(repo_root, ["rev-parse", "HEAD"])


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


def _summary_generation_command(*, args: argparse.Namespace, repo_root: Path) -> str:
    parts = [
        "quality-runner",
        "summarize-run",
        str(repo_root),
        "--run-id",
        str(args.run_id),
    ]
    if args.baseline_run_id:
        parts.extend(["--baseline-run-id", str(args.baseline_run_id)])
    parts.extend(["--controller-report", "--json"])
    if args.report_output:
        parts.extend(["--report-output", str(Path(args.report_output).expanduser().resolve())])
    return " ".join(parts)


def _lint_command(output_path: Path | None) -> str:
    target = str(output_path) if output_path else "<generated-report>"
    return f"quality-runner controller-report lint {target} --strict --json"


def _validate_command(output_path: Path | None) -> str:
    target = str(output_path) if output_path else "<generated-report>"
    return f"quality-runner validate-report {target} --json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
