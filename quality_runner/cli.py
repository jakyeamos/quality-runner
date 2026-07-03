from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from quality_runner import __version__
from quality_runner.code_quality import preview_ignored_paths
from quality_runner.config import CONFIG_FILE_NAME, load_repo_config
from quality_runner.controller_reports import validate_controller_report
from quality_runner.standards import DEFAULT_PROFILE
from quality_runner.workflow import inspect_payload, run_payload, verify_gates_payload

DOCTOR_RESULT_SCHEMA = "quality-runner-doctor-result-v0.1"
EXPORT_HANDOFF_RESULT_SCHEMA = "quality-runner-export-handoff-result-v0.1"
INIT_RESULT_SCHEMA = "quality-runner-init-result-v0.1"
STATUS_RESULT_SCHEMA = "quality-runner-status-result-v0.1"
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

    doctor_parser = subparsers.add_parser("doctor", help="Check Quality Runner readiness")
    doctor_parser.add_argument("--json", action="store_true", help="Emit JSON output")

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
            print(_human_summary(payload))
    elif getattr(parsed, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_human_summary(payload))
    if parsed.command == "validate-report" and payload.get("status") == "rejected":
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
    if args.command == "init":
        return _init_payload(
            repo_root=_validated_repo_path(args.repo_path),
            profile=args.profile,
            required_capabilities=args.required_capability,
            force=args.force,
        )
    if args.command == "status":
        return _status_payload(repo_root=_validated_repo_path(args.repo_path))
    if args.command == "export-handoff":
        return _export_handoff_payload(
            repo_root=_validated_repo_path(args.repo_path),
            run_id=args.run_id,
            output_path=Path(args.output).expanduser().resolve() if args.output else None,
        )
    if args.command == "validate-report":
        return validate_controller_report(_load_report_json(Path(args.report_json)))
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
        )
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


def _status_payload(repo_root: Path) -> dict[str, Any]:
    latest_run = _latest_run(repo_root)
    status = _repo_status(latest_run)
    return {
        "schema": STATUS_RESULT_SCHEMA,
        "status": status,
        "repo_root": str(repo_root),
        "implementation_allowed": False,
        "config": load_repo_config(repo_root),
        "latest_run": latest_run,
    }


def _export_handoff_payload(
    *,
    repo_root: Path,
    run_id: str | None,
    output_path: Path | None,
) -> dict[str, Any]:
    resolved_run_id = _latest_run_id(repo_root) if run_id is None else run_id
    if resolved_run_id is None:
        raise FileNotFoundError("no Quality Runner runs found")

    handoff_path = repo_root / ".quality-runner" / "runs" / resolved_run_id / "agent-handoff.md"
    if not handoff_path.exists():
        raise FileNotFoundError(f"agent handoff does not exist for run: {resolved_run_id}")
    content = handoff_path.read_text(encoding="utf-8")

    payload = {
        "schema": EXPORT_HANDOFF_RESULT_SCHEMA,
        "status": "exported",
        "run_id": resolved_run_id,
        "source_path": str(handoff_path),
        "implementation_allowed": False,
    }
    if output_path is None:
        payload["content"] = content
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        payload["output_path"] = str(output_path)
    return payload


def _load_report_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"controller report is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError("controller report JSON must contain an object")
    return payload


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


def _latest_run(repo_root: Path) -> dict[str, Any] | None:
    run_id = _latest_run_id(repo_root)
    if run_id is None:
        return None
    run_dir = repo_root / ".quality-runner" / "runs" / run_id
    gate_verification_status = _gate_verification_status(run_dir)
    return {
        "run_id": run_id,
        "path": str(run_dir),
        "has_handoff": (run_dir / "agent-handoff.md").exists(),
        "has_audit": (run_dir / "quality-audit.json").exists(),
        "has_gate_verification": gate_verification_status is not None,
        "gate_verification_status": gate_verification_status,
    }


def _repo_status(latest_run: dict[str, Any] | None) -> str:
    if latest_run is None:
        return "initialized"
    gate_status = latest_run.get("gate_verification_status")
    if gate_status in {"failed", "blocked"}:
        return "blocked"
    return "ready"


def _gate_verification_status(run_dir: Path) -> str | None:
    path = run_dir / "gate-verification.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return "blocked"
    status = payload.get("status")
    return status if isinstance(status, str) and status else "blocked"


def _latest_run_id(repo_root: Path) -> str | None:
    runs_dir = repo_root / ".quality-runner" / "runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        return None
    candidates = [path for path in runs_dir.iterdir() if path.is_dir()]
    if not candidates:
        return None
    latest = max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))
    return latest.name


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            unique.append(value)
            seen.add(value)
    return unique


def _human_summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "unknown")
    if payload.get("schema") == DOCTOR_RESULT_SCHEMA:
        version = payload.get("version", __version__)
        return f"Quality Runner {version}: {status}"
    if payload.get("schema") == INIT_RESULT_SCHEMA:
        return f"config: {payload.get('config_path')}"
    if payload.get("schema") == STATUS_RESULT_SCHEMA:
        latest = payload.get("latest_run")
        run_id = latest.get("run_id") if isinstance(latest, dict) else "none"
        return f"status: {status}\nlatest run: {run_id}"
    if payload.get("schema") == EXPORT_HANDOFF_RESULT_SCHEMA:
        output_path = payload.get("output_path")
        if isinstance(output_path, str):
            return f"handoff: {output_path}"
        return f"handoff: {payload.get('source_path')}"

    lines = [f"status: {status}"]
    run_id = payload.get("run_id")
    if isinstance(run_id, str):
        lines.append(f"run id: {run_id}")

    artifact_paths = payload.get("artifact_paths")
    if isinstance(artifact_paths, dict):
        handoff_path = artifact_paths.get("agent_handoff_md")
        audit_path = artifact_paths.get("quality_audit_json")
        repo_scan_path = artifact_paths.get("repo_scan_json")
        if isinstance(handoff_path, str):
            lines.append(f"handoff: {handoff_path}")
        if isinstance(audit_path, str):
            lines.append(f"audit: {audit_path}")
        elif isinstance(repo_scan_path, str):
            lines.append(f"repo scan: {repo_scan_path}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
