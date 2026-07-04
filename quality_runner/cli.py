from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from quality_runner import __version__
from quality_runner.cli_controller_reports import (
    add_controller_report_command,
    add_controller_report_summary_arguments,
    controller_report_command_payload,
    controller_report_from_summary_payload,
    has_rejected_self_check,
    load_controller_report_json,
)
from quality_runner.cli_human_summary import human_summary
from quality_runner.cli_refresh import refresh_command_payload
from quality_runner.cli_rollout import add_rollout_command, rollout_command_payload
from quality_runner.cli_status import (
    export_handoff_payload,
    status_payload,
)
from quality_runner.code_quality import preview_ignored_paths
from quality_runner.config import CONFIG_FILE_NAME, load_repo_config
from quality_runner.controller_reports import validate_controller_report
from quality_runner.release_smoke import release_smoke_payload
from quality_runner.run_summary import build_run_summary
from quality_runner.standards import DEFAULT_PROFILE
from quality_runner.workflow import (
    inspect_payload,
    run_payload,
    verify_gates_payload,
)

DOCTOR_RESULT_SCHEMA = "quality-runner-doctor-result-v0.1"
INIT_RESULT_SCHEMA = "quality-runner-init-result-v0.1"
EXPENSIVE_IGNORED_PATH_TEXT_FILE_THRESHOLD = 100
EXPENSIVE_IGNORED_PATH_SECONDS_THRESHOLD = 5.0
MAX_INTERACTIVE_IGNORED_PATHS = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quality-runner",
        description="Audit a repo and produce an evidence-backed remediation plan.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Inspect a repo and write audit artifacts")
    _add_workflow_arguments(run_parser)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a repo without audit planning")
    _add_workflow_arguments(inspect_parser)

    verify_parser = subparsers.add_parser("verify-gates", help="Execute discovered repo gates")
    _add_workflow_arguments(verify_parser)
    verify_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Per-gate command timeout",
    )
    verify_parser.add_argument(
        "--read-only-gates",
        action="store_true",
        help="Skip gates that are known or likely to mutate source files",
    )
    verify_parser.add_argument(
        "--allow-mutating-gates",
        action="store_true",
        help="Allow known or suspected mutating gates to execute",
    )

    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Run inspect, run, verify-gates, summarize, and optionally export a handoff",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Use --handoff-output to write a remediation handoff in the same command.\n\n"
            "Refresh emits gate handoff statuses for controller routing:\n"
            "  gates-clean    all discovered local gates passed\n"
            "  gates-blocked  environment, dependency setup, or read-only policy blocked evidence\n"
            "  gates-failed   executable repo gates ran and failed\n\n"
            "Blocked and failed handoffs include gate_verification.blocker_groups and\n"
            "next_slice.action_groups. Use --total-timeout-reason to record why a\n"
            "full refresh deadline was applied when --total-timeout-seconds is set."
        ),
    )
    _add_workflow_arguments(refresh_parser)
    refresh_parser.add_argument(
        "--run-id-prefix",
        required=True,
        help="Prefix used to create <prefix>-inspect, <prefix>-run, and <prefix>-verify runs",
    )
    refresh_parser.add_argument(
        "--baseline-run-id", default=None, help="Baseline run id for deltas"
    )
    refresh_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Per-gate command timeout",
    )
    refresh_parser.add_argument(
        "--workflow-timeout-seconds",
        type=int,
        default=None,
        help=(
            "Backward-compatible alias for --verify-timeout-seconds; "
            "applies only to the verify-gates phase"
        ),
    )
    refresh_parser.add_argument(
        "--verify-timeout-seconds",
        type=int,
        default=None,
        help="Verify-gates phase timeout; defaults to a multiple of --timeout-seconds",
    )
    refresh_parser.add_argument(
        "--workflow-timeout-reason",
        default=None,
        help="Reason recorded when the verify-gates timeout fires",
    )
    refresh_parser.add_argument(
        "--total-timeout-seconds",
        type=int,
        default=None,
        help="Optional hard deadline for the full refresh across inspect, run, and verify",
    )
    refresh_parser.add_argument(
        "--total-timeout-reason",
        default=None,
        help="Reason recorded when the total refresh timeout fires",
    )
    refresh_parser.add_argument(
        "--allow-mutating-gates",
        action="store_true",
        help="Allow known or suspected mutating gates to execute during refresh",
    )
    refresh_parser.add_argument(
        "--handoff-output",
        default=None,
        help="Write the generated remediation handoff markdown to this path",
    )

    add_rollout_command(subparsers)

    init_parser = subparsers.add_parser("init", help="Write a starter .quality-runner.toml")
    init_parser.add_argument("repo_path", help="Target repository path")
    init_parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Default standards profile")
    init_parser.add_argument(
        "--required-capability",
        action="append",
        default=[],
        help="Required capability to add to the starter config",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing config")
    init_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    status_parser = subparsers.add_parser("status", help="Show repo Quality Runner state")
    status_parser.add_argument("repo_path", help="Target repository path")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    summary_parser = subparsers.add_parser(
        "summarize-run", help="Summarize a Quality Runner run and optional baseline delta"
    )
    summary_parser.add_argument("repo_path", help="Target repository path")
    summary_parser.add_argument("--run-id", required=True, help="Run id to summarize")
    summary_parser.add_argument(
        "--baseline-run-id", default=None, help="Baseline run id for deltas"
    )
    add_controller_report_summary_arguments(summary_parser)
    summary_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    export_parser = subparsers.add_parser("export-handoff", help="Print or write an agent handoff")
    export_parser.add_argument("repo_path", help="Target repository path")
    export_parser.add_argument("--run-id", default=None, help="Run id to export")
    export_parser.add_argument("--output", default=None, help="Write handoff markdown to this path")
    export_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    validate_report_parser = subparsers.add_parser(
        "validate-report", help="Validate a controller thread completion report"
    )
    validate_report_parser.add_argument("report_json", help="Controller report JSON path")
    validate_report_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    add_controller_report_command(subparsers)

    doctor_parser = subparsers.add_parser("doctor", help="Check Quality Runner readiness")
    doctor_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    release_smoke_parser = subparsers.add_parser(
        "release-smoke",
        help="Run pre-release CLI, refresh, handoff, and schema smoke checks",
    )
    release_smoke_parser.add_argument(
        "--work-dir",
        default=None,
        help="Directory for temporary release-smoke repo and handoff outputs",
    )
    release_smoke_parser.add_argument("--json", action="store_true", help="Emit JSON output")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print(f"Quality Runner {__version__}")
        print("Run 'quality-runner --help' for usage.")
        return 0

    parser = build_parser()
    try:
        parsed = parser.parse_args(args)
    except SystemExit as error:
        code = error.code
        return code if isinstance(code, int) else 2

    try:
        payload = _payload_for_args(parsed)
    except (FileNotFoundError, NotADirectoryError, ValueError, OSError) as error:
        print(f"quality-runner: error: {error}", file=sys.stderr)
        return 1

    if parsed.command == "export-handoff" and not getattr(parsed, "json", False):
        content = payload.get("content")
        if isinstance(content, str):
            print(content, end="" if content.endswith("\n") else "\n")
        else:
            print(human_summary(payload))
    elif getattr(parsed, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(human_summary(payload))
    if (
        parsed.command in {"validate-report", "controller-report"}
        and payload.get("status") == "rejected"
    ):
        return 1
    if parsed.command == "release-smoke" and payload.get("status") != "passed":
        return 1
    if parsed.command == "summarize-run" and has_rejected_self_check(payload):
        return 1
    return 0


def _add_workflow_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument("--run-id", default=None, help="Stable run id")
    parser.add_argument("--profile", default=None, help="Standards profile override")
    parser.add_argument(
        "--ci-status-json",
        default=None,
        help="Local CI status JSON export to attach to capability evidence",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt before excluding expensive default-ignored scan paths",
    )
    parser.add_argument(
        "--checkout-most-advanced-branch",
        action="store_true",
        help="Switch to the local branch with the highest commit count before scanning",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def _payload_for_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "doctor":
        return _doctor_payload()
    if args.command == "release-smoke":
        return release_smoke_payload(
            work_dir=Path(args.work_dir) if args.work_dir else None,
            help_text=build_parser().format_help(),
        )
    if args.command == "init":
        return _init_payload(
            repo_root=_validated_repo_path(args.repo_path),
            profile=args.profile,
            required_capabilities=args.required_capability,
            force=args.force,
        )
    if args.command == "status":
        return status_payload(repo_root=_validated_repo_path(args.repo_path))
    if args.command == "summarize-run":
        repo_root = _validated_repo_path(args.repo_path)
        summary = build_run_summary(
            repo_root=repo_root,
            run_id=args.run_id,
            baseline_run_id=args.baseline_run_id,
        )
        if args.controller_report:
            return controller_report_from_summary_payload(
                args=args,
                repo_root=repo_root,
                summary=summary,
            )
        return summary
    if args.command == "controller-report":
        return controller_report_command_payload(args)
    if args.command == "export-handoff":
        return export_handoff_payload(
            repo_root=_validated_repo_path(args.repo_path),
            run_id=args.run_id,
            output_path=Path(args.output).expanduser().resolve() if args.output else None,
        )
    if args.command == "validate-report":
        return validate_controller_report(load_controller_report_json(Path(args.report_json)))
    if args.command == "run":
        repo_root = _validated_repo_path(args.repo_path)
        return run_payload(
            repo_root=repo_root,
            run_id=args.run_id,
            profile=args.profile,
            ci_status_json=Path(args.ci_status_json) if args.ci_status_json else None,
            include_ignored_paths=_interactive_include_ignored_paths(args, repo_root),
            checkout_most_advanced_branch=args.checkout_most_advanced_branch,
        )
    if args.command == "inspect":
        repo_root = _validated_repo_path(args.repo_path)
        return inspect_payload(
            repo_root=repo_root,
            run_id=args.run_id,
            profile=args.profile,
            ci_status_json=Path(args.ci_status_json) if args.ci_status_json else None,
            include_ignored_paths=_interactive_include_ignored_paths(args, repo_root),
            checkout_most_advanced_branch=args.checkout_most_advanced_branch,
        )
    if args.command == "verify-gates":
        repo_root = _validated_repo_path(args.repo_path)
        return verify_gates_payload(
            repo_root=repo_root,
            run_id=args.run_id,
            profile=args.profile,
            ci_status_json=Path(args.ci_status_json) if args.ci_status_json else None,
            timeout_seconds=args.timeout_seconds,
            checkout_most_advanced_branch=args.checkout_most_advanced_branch,
            read_only_gates=args.read_only_gates,
            allow_mutating_gates=args.allow_mutating_gates,
        )
    if args.command == "refresh":
        repo_root = _validated_repo_path(args.repo_path)
        return refresh_command_payload(args, repo_root)
    if args.command == "rollout":
        return rollout_command_payload(args)
    raise ValueError(f"unsupported command: {args.command}")


def _doctor_payload() -> dict[str, Any]:
    return {
        "schema": DOCTOR_RESULT_SCHEMA,
        "status": "ready",
        "version": __version__,
        "implementation_allowed": False,
        "environment": {
            "cwd": str(Path.cwd()),
            "platform": platform.platform(),
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
        },
    }


def _init_payload(
    *,
    repo_root: Path,
    profile: str,
    required_capabilities: list[str],
    force: bool,
) -> dict[str, Any]:
    config_path = repo_root / CONFIG_FILE_NAME
    if config_path.exists() and not force:
        raise ValueError(f"{CONFIG_FILE_NAME} already exists")

    unique_capabilities = _unique_strings(required_capabilities)
    content = (
        "[quality_runner]\n"
        f'default_profile = "{profile}"\n'
        f"required_capabilities = {json.dumps(unique_capabilities)}\n"
    )
    config_path.write_text(content, encoding="utf-8")

    return {
        "schema": INIT_RESULT_SCHEMA,
        "status": "created" if not force else "written",
        "config_path": str(config_path),
        "implementation_allowed": False,
    }


def _validated_repo_path(repo_path: str) -> Path:
    root = Path(repo_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"repo root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"repo root is not a directory: {root}")
    return root


def _interactive_include_ignored_paths(args: argparse.Namespace, repo_root: Path) -> list[str]:
    if not _should_prompt_for_ignored_paths(args):
        return []

    preview = preview_ignored_paths(repo_root, config=load_repo_config(repo_root))
    expensive = [
        item
        for item in preview
        if _int_value(item.get("estimated_text_files"))
        >= EXPENSIVE_IGNORED_PATH_TEXT_FILE_THRESHOLD
        or _float_value(item.get("estimated_scan_seconds"))
        >= EXPENSIVE_IGNORED_PATH_SECONDS_THRESHOLD
        or item.get("estimate_truncated") is True
    ]
    if not expensive:
        return []

    _print_ignored_path_prompt(expensive)
    answer = sys.stdin.readline().strip().lower()
    if answer in {"n", "no"}:
        paths = [item["path"] for item in expensive if isinstance(item.get("path"), str)]
        print("Scanning these paths for this run only.", file=sys.stderr)
        return paths
    print("Keeping these paths excluded for this run.", file=sys.stderr)
    return []


def _should_prompt_for_ignored_paths(args: argparse.Namespace) -> bool:
    if getattr(args, "interactive", False):
        return True
    return not getattr(args, "json", False) and sys.stdin.isatty() and sys.stderr.isatty()


def _print_ignored_path_prompt(paths: list[dict[str, Any]]) -> None:
    print(
        "Quality Runner found default-excluded paths that would expand the scan surface:",
        file=sys.stderr,
    )
    for item in paths[:MAX_INTERACTIVE_IGNORED_PATHS]:
        path = item.get("path")
        files = _int_value(item.get("estimated_text_files"))
        seconds = _float_value(item.get("estimated_scan_seconds"))
        truncated = "+" if item.get("estimate_truncated") is True else ""
        print(f"- {path}: ~{files}{truncated} text files, ~{seconds:.1f}s", file=sys.stderr)
    remaining = len(paths) - MAX_INTERACTIVE_IGNORED_PATHS
    if remaining > 0:
        print(f"- ...and {remaining} more paths", file=sys.stderr)
    print(
        "Default is to exclude them. To always scan one, add its path to "
        "quality_runner.structural_scan.include_ignored_paths.",
        file=sys.stderr,
    )
    print("Exclude these paths from this run? [Y/n] ", end="", file=sys.stderr, flush=True)


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _float_value(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            unique.append(value)
            seen.add(value)
    return unique


if __name__ == "__main__":
    raise SystemExit(main())
