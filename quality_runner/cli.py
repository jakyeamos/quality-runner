from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from quality_runner import __version__
from quality_runner.workflow import inspect_payload, run_payload

DOCTOR_RESULT_SCHEMA = "quality-runner-doctor-result-v0.1"


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

    if getattr(parsed, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_human_summary(payload))
    return 0


def _add_workflow_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument("--run-id", default=None, help="Stable run id")
    parser.add_argument("--profile", default="jakyeamos", help="Standards profile")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def _payload_for_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "doctor":
        return _doctor_payload()
    if args.command == "run":
        return run_payload(
            repo_root=_validated_repo_path(args.repo_path),
            run_id=args.run_id,
            profile=args.profile,
        )
    if args.command == "inspect":
        return inspect_payload(
            repo_root=_validated_repo_path(args.repo_path),
            run_id=args.run_id,
            profile=args.profile,
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


def _validated_repo_path(repo_path: str) -> Path:
    root = Path(repo_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"repo root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"repo root is not a directory: {root}")
    return root


def _human_summary(payload: dict[str, Any]) -> str:
    status = payload.get("status", "unknown")
    if payload.get("schema") == DOCTOR_RESULT_SCHEMA:
        version = payload.get("version", __version__)
        return f"Quality Runner {version}: {status}"

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
