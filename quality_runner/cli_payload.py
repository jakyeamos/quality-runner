from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any, cast

from quality_runner import __version__
from quality_runner.application.outcome_projection import LegacyPayload
from quality_runner.cli_controller_reports import (
    controller_report_command_payload,
    controller_report_from_summary_payload,
    load_controller_report_json,
)
from quality_runner.cli_fix_proposals import propose_fix_command_payload
from quality_runner.cli_gate import (
    gate_command_payload,
    gate_respond_command_payload,
    gate_status_command_payload,
)
from quality_runner.cli_handoff import handoff_command_payload
from quality_runner.cli_refresh import refresh_command_payload
from quality_runner.cli_review import review_command_payload
from quality_runner.cli_rollout import rollout_command_payload
from quality_runner.cli_skills import skill_command_payload
from quality_runner.cli_status import export_handoff_payload, status_payload
from quality_runner.code_quality import preview_ignored_paths
from quality_runner.compatibility.journey_outcomes import (
    audit_journey_outcome,
    review_journey_outcome,
    runs_journey_outcome,
    verify_journey_outcome,
)
from quality_runner.config import CONFIG_FILE_NAME, load_repo_config
from quality_runner.controller_reports import validate_controller_report
from quality_runner.intent import workflow_intent_from_cli_args
from quality_runner.release_smoke import release_smoke_payload
from quality_runner.run_summary import build_run_summary
from quality_runner.workflow import inspect_payload, run_payload, verify_gates_payload
from quality_runner.workflow_skills import load_skill_review_report_json

DOCTOR_RESULT_SCHEMA = "quality-runner-doctor-result-v0.1"
INIT_RESULT_SCHEMA = "quality-runner-init-result-v0.1"
EXPENSIVE_IGNORED_PATH_TEXT_FILE_THRESHOLD = 100
EXPENSIVE_IGNORED_PATH_SECONDS_THRESHOLD = 5.0
MAX_INTERACTIVE_IGNORED_PATHS = 10


def payload_for_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "doctor":
        return _doctor_payload()
    if args.command == "release-smoke":
        from quality_runner.cli import build_parser

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
    if args.command == "runs":
        return _result_payload(
            runs_journey_outcome(
                repo_root=_validated_repo_path(args.repo_path),
                run_id=args.run_id,
                limit=args.limit,
            )
        )
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
            output_path=Path(args.output).expanduser() if args.output else None,
        )
    if args.command in {"validate-skill-review", "skill"}:
        return skill_command_payload(args, validated_repo_path=_validated_repo_path)
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
            skill_review_report=_optional_skill_review_report(args),
            intent=workflow_intent_from_cli_args(args, repo_root=repo_root, run_id=args.run_id),
        )
    if args.command == "audit":
        repo_root = _validated_repo_path(args.repo_path)
        return _result_payload(
            audit_journey_outcome(
                repo_root=repo_root,
                run_id=args.run_id,
                profile=args.profile,
                ci_status_json=Path(args.ci_status_json) if args.ci_status_json else None,
                include_ignored_paths=_interactive_include_ignored_paths(args, repo_root),
                checkout_most_advanced_branch=args.checkout_most_advanced_branch,
                skill_review_report=_legacy_payload(_optional_skill_review_report(args)),
                intent=_legacy_payload(
                    workflow_intent_from_cli_args(args, repo_root=repo_root, run_id=args.run_id)
                ),
                inspect_only=args.inspect_only,
            )
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
            skill_review_report=_optional_skill_review_report(args),
            intent=workflow_intent_from_cli_args(args, repo_root=repo_root, run_id=args.run_id),
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
            execute_discovered_gates=getattr(args, "execute_gates", False),
            read_only_gates=args.read_only_gates,
            allow_mutating_gates=args.allow_mutating_gates,
            worktree_mode=args.worktree_mode,
            allow_dirty_worktree_verify=args.allow_dirty_worktree_verify,
            skill_review_report=_optional_skill_review_report(args),
            intent=workflow_intent_from_cli_args(args, repo_root=repo_root, run_id=args.run_id),
        )
    if args.command == "verify":
        repo_root = _validated_repo_path(args.repo_path)
        return _result_payload(
            verify_journey_outcome(
                repo_root=repo_root,
                run_id=args.run_id,
                profile=args.profile,
                ci_status_json=Path(args.ci_status_json) if args.ci_status_json else None,
                timeout_seconds=args.timeout_seconds,
                checkout_most_advanced_branch=args.checkout_most_advanced_branch,
                execute_discovered_gates=args.execute_gates,
                read_only_gates=args.read_only_gates,
                allow_mutating_gates=args.allow_mutating_gates,
                worktree_mode=args.worktree_mode,
                allow_dirty_worktree_verify=args.allow_dirty_worktree_verify,
                skill_review_report=_legacy_payload(_optional_skill_review_report(args)),
                intent=_legacy_payload(
                    workflow_intent_from_cli_args(args, repo_root=repo_root, run_id=args.run_id)
                ),
            )
        )
    if args.command == "refresh":
        return refresh_command_payload(args, _validated_repo_path(args.repo_path))
    if args.command == "rollout":
        return rollout_command_payload(args)
    if args.command == "review":
        repo_root = _validated_repo_path(args.repo_path)
        payload = review_command_payload(
            args,
            repo_root,
            include_extended_artifacts=bool(getattr(args, "outcome", False)),
        )
        if getattr(args, "outcome", False):
            return _result_payload(
                review_journey_outcome(cast(LegacyPayload, payload), repo_root=repo_root)
            )
        return payload
    if args.command == "gate":
        return gate_command_payload(args, repo_root=_validated_repo_path(args.repo_path))
    if args.command == "gate-status":
        return gate_status_command_payload(args, repo_root=_validated_repo_path(args.repo_path))
    if args.command == "gate-respond":
        return gate_respond_command_payload(args, repo_root=_validated_repo_path(args.repo_path))
    if args.command in {
        "export-slice-specs",
        "validate-handoff",
        "validate-slice-spec",
        "review-worker",
    }:
        return handoff_command_payload(args)
    if args.command == "propose-fix":
        return propose_fix_command_payload(args, repo_root=_validated_repo_path(args.repo_path))
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


def _optional_skill_review_report(args: argparse.Namespace) -> dict[str, Any] | None:
    report_path = getattr(args, "skill_review_report", None)
    if not report_path:
        return None
    return load_skill_review_report_json(Path(report_path).expanduser().resolve())


def _legacy_payload(payload: dict[str, Any] | None) -> LegacyPayload | None:
    return cast(LegacyPayload | None, payload)


def _result_payload(payload: object) -> dict[str, Any]:
    return cast(dict[str, Any], payload)


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
