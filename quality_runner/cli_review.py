from __future__ import annotations

import argparse
import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from quality_runner.application.fresh_review import (
    complete_fresh_review,
    incomplete_fresh_review,
    prepare_fresh_review,
)
from quality_runner.application.review_context_factory import normalize_review_options
from quality_runner.application.review_v1_reports import review_report_to_v1
from quality_runner.core.review_contracts import (
    EvidenceReference,
    FreshReviewExecution,
    NormalizedReviewOptions,
    ReviewLoopStop,
)
from quality_runner.review_response_files import (
    ReviewAdapterResponseError,
    ReviewAdapterResponsePermissionError,
)
from quality_runner.workflow_internal import generated_run_id

REVIEW_RESULT_SCHEMA = "quality-runner-review-result-v0.1"
MAX_TASK_FILE_BYTES = 262_144


def review_mcp_tool() -> dict[str, object]:
    return {
        "name": "quality_runner_review",
        "description": (
            "Run a fresh local read-only review and write canonical v1 artifacts; "
            "supported through 0.7.x. Prefer quality_runner_review_outcome."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_root": {"type": "string"},
                "run_id": {"type": "string"},
                "mode": {"enum": ["task", "blind", "combined"]},
                "scope": {"enum": ["task", "project"]},
                "breadth": {"enum": ["focused", "related", "full"]},
                "task": {"type": "string"},
                "task_file": {"type": "string"},
                "previous_summary": {"type": "string"},
                "exclude": {"type": "array", "items": {"type": "string"}},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "detail": {"enum": ["standard", "concise", "full", "expanded"]},
                "save": {"type": "boolean"},
                "known_issues": {"type": "array", "items": {"type": "string"}},
                "loop": {"type": "boolean"},
                "loop_stop": {
                    "oneOf": [
                        {"type": "boolean"},
                        {"enum": ["critical-high", "none"]},
                    ]
                },
                "finding_id": {"type": "array", "items": {"type": "string"}},
                "all_critical_high": {"type": "boolean"},
                "adapter_output": {"type": "string"},
            },
            "required": ["repo_root"],
            "additionalProperties": False,
        },
    }


def review_mcp_payload(
    arguments: Mapping[str, object],
    repo_root: Path,
    *,
    include_extended_artifacts: bool = False,
) -> dict[str, object]:
    def strings(key: str) -> list[str]:
        value = arguments.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{key} must be an array of strings")
        return value

    args = argparse.Namespace(
        command="review",
        repo_path=str(repo_root),
        run_id=_optional_string(arguments, "run_id"),
        mode=_string_or_default(arguments, "mode", "task"),
        scope=_string_or_default(arguments, "scope", "project"),
        breadth=_optional_string(arguments, "breadth"),
        task=_optional_string(arguments, "task"),
        task_file=_optional_string(arguments, "task_file"),
        reuse_task=False,
        previous_summary=_optional_string(arguments, "previous_summary"),
        exclude=strings("exclude"),
        evidence=strings("evidence"),
        detail=_string_or_default(arguments, "detail", "standard"),
        save=_bool_or_default(arguments, "save", True),
        known_issues=strings("known_issues"),
        loop=_bool_or_default(arguments, "loop", False),
        loop_stop=_loop_stop(arguments),
        finding_id=strings("finding_id"),
        all_critical_high=_bool_or_default(arguments, "all_critical_high", False),
        adapter_output=_optional_string(arguments, "adapter_output"),
    )
    return review_command_payload(
        args,
        repo_root,
        include_extended_artifacts=include_extended_artifacts,
    )


def add_review_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("review", help="Run a fresh, read-only review")
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument("--run-id", default=None, help="Stable review run id")
    parser.add_argument("--mode", choices=["task", "blind", "combined"], default="task")
    parser.add_argument("--scope", choices=["task", "project"], default="project")
    parser.add_argument("--breadth", choices=["focused", "related", "full"], default=None)
    parser.add_argument("--task", default=None, help="Task or acceptance criteria under review")
    parser.add_argument("--task-file", default=None, help="Read task text from a local file")
    parser.add_argument(
        "--reuse-task", action="store_true", help="Reuse --previous-summary as task context"
    )
    parser.add_argument("--previous-summary", default=None)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument(
        "--detail",
        choices=["standard", "concise", "full", "expanded"],
        default="standard",
        help="Packet detail hint; expanded remains a compatibility alias for full",
    )
    parser.add_argument("--save", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--known-issues", action="append", default=[])
    parser.add_argument(
        "--loop-stop",
        nargs="?",
        const="critical-high",
        choices=["critical-high", "none"],
        default=None,
        help="Stop an active review loop at critical/high or no findings during response submission",
    )
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--finding-id", action="append", default=[])
    parser.add_argument("--all-critical-high", action="store_true")
    parser.add_argument(
        "--adapter-output",
        default=None,
        help="Local adapter result JSON inside the run artifact directory",
    )
    parser.add_argument(
        "--outcome",
        action="store_true",
        help="Compatibility alias; the v2 journey outcome is now the default",
    )
    parser.add_argument(
        "--legacy-output",
        action="store_true",
        help="Emit the established v1 result projection (supported through 0.7.x)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def review_command_payload(
    args: argparse.Namespace,
    repo_root: Path,
    *,
    include_extended_artifacts: bool = False,
) -> dict[str, object]:
    run_id = args.run_id or f"{generated_run_id()}-review"
    loop_stop = _resolved_loop_stop(args.loop_stop)
    if args.adapter_output:
        if args.run_id is None:
            raise ValueError("--adapter-output requires --run-id for a prepared review packet")
        if args.save is False:
            raise ValueError("--adapter-output requires saved review artifacts; omit --no-save")
        try:
            execution = complete_fresh_review(
                repo_root=repo_root,
                run_id=run_id,
                response_path=Path(args.adapter_output),
                finding_ids=args.finding_id,
                all_critical_high=args.all_critical_high,
                loop=args.loop,
                loop_stop=loop_stop,
            )
        except ReviewAdapterResponsePermissionError as error:
            execution = incomplete_fresh_review(
                repo_root=repo_root,
                run_id=run_id,
                status="permission-denied",
                message=str(error),
            )
        except ReviewAdapterResponseError as error:
            execution = incomplete_fresh_review(
                repo_root=repo_root,
                run_id=run_id,
                status="malformed-output",
                message=str(error),
            )
        return _legacy_result_payload(
            execution,
            include_extended_artifacts=include_extended_artifacts,
        )
    if args.finding_id or args.all_critical_high:
        raise ValueError(
            "--finding-id and --all-critical-high require a completed --adapter-output review"
        )
    if loop_stop is not None:
        raise ValueError("--loop-stop requires a completed --adapter-output review")
    task = _task_input(args, repo_root)
    if args.reuse_task and not task:
        task = args.previous_summary
    if args.mode in {"task", "combined"} and not task:
        raise ValueError(
            "task mode requires --task or --task-file; use --mode blind for a fresh blind review"
        )
    evidence, omitted = _evidence(repo_root, args.evidence)
    options = normalize_review_options(
        mode=args.mode,
        scope=args.scope,
        breadth=args.breadth,
        task=task,
        exclusions=args.exclude,
        evidence=evidence,
        known_issues=args.known_issues,
        include_known_issues=bool(args.known_issues),
        previous_summary=args.previous_summary,
        active_cycle=bool(args.loop),
    )
    execution = prepare_fresh_review(
        repo_root=repo_root,
        run_id=run_id,
        options=cast(NormalizedReviewOptions, options),
        repository_state={"detail": "full" if args.detail == "expanded" else args.detail},
        changed_files=_changed_files(repo_root),
        omitted_evidence=omitted,
        save=args.save,
    )
    return _legacy_result_payload(execution, include_extended_artifacts=include_extended_artifacts)


def _legacy_result_payload(
    execution: FreshReviewExecution,
    *,
    include_extended_artifacts: bool = False,
) -> dict[str, object]:
    context = execution["context"]
    report = execution["report"]
    status = report["adapter_status"]
    artifact_paths = {
        key: value
        for key, value in execution["artifact_paths"].items()
        if key
        in {
            "review_manifest_json",
            "review_context_json",
            "review_report_json",
            "review_report_md",
            "review_agent_packet_md",
            "review_fix_prompts_md",
        }
    }
    if include_extended_artifacts:
        artifact_paths = dict(execution["artifact_paths"])
    next_action = report.get("next_action")
    return {
        "schema": REVIEW_RESULT_SCHEMA,
        "status": status,
        "run_id": context["run_id"],
        "mode": context["mode"],
        "scope": context["scope"],
        "breadth": context["breadth"],
        "adapter_status": status,
        "outcome": "packet-ready" if status == "review-not-run" else status,
        "summary": report["summary"],
        "severity_counts": report["severity_counts"],
        "evidence_unavailable": list(report["evidence_unavailable"]),
        "artifact_paths": artifact_paths,
        "saved_path": artifact_paths.get("review_report_json"),
        **({"next_action": next_action} if isinstance(next_action, str) and next_action else {}),
        "report": review_report_to_v1(report),
    }


def _task_input(args: argparse.Namespace, repo_root: Path) -> str | None:
    if args.task_file:
        return _read_task_file(Path(args.task_file), repo_root=repo_root)
    return args.task.strip() if isinstance(args.task, str) and args.task.strip() else None


def _read_task_file(path: Path, *, repo_root: Path) -> str:
    root = repo_root.expanduser().resolve()
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    if candidate.is_symlink():
        raise ValueError("task file must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except FileNotFoundError as error:
        raise FileNotFoundError(f"task file does not exist: {candidate}") from error
    except ValueError as error:
        raise ValueError("task file must remain inside the target repository") from error
    root_descriptor: int | None = None
    directory_descriptor: int | None = None
    descriptor: int | None = None
    try:
        root_descriptor = os.open(
            root,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        directory_descriptor = root_descriptor
        relative = resolved.relative_to(root)
        if not relative.parts:
            raise ValueError("task file must be a regular file")
        for segment in relative.parts[:-1]:
            next_descriptor = os.open(
                segment,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_descriptor,
            )
            if directory_descriptor != root_descriptor:
                os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        filename = relative.name
        descriptor = os.open(
            filename,
            os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_descriptor,
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("task file must be a regular file")
        if metadata.st_size > MAX_TASK_FILE_BYTES:
            raise ValueError("task file exceeds the review input limit")
        chunks: list[bytes] = []
        remaining = MAX_TASK_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining == 0:
            raise ValueError("task file exceeds the review input limit")
        return b"".join(chunks).decode("utf-8").strip()
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory_descriptor is not None and directory_descriptor != root_descriptor:
            os.close(directory_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)


def _evidence(repo_root: Path, paths: list[str]) -> tuple[list[EvidenceReference], list[str]]:
    references: list[EvidenceReference] = []
    omitted: list[str] = []
    root = repo_root.resolve()
    for raw in paths:
        candidate = root / raw if not Path(raw).is_absolute() else Path(raw).expanduser()
        if candidate.is_symlink():
            omitted.append(f"symlinked evidence: {raw}")
            continue
        path = candidate.resolve()
        try:
            path.relative_to(root)
        except ValueError:
            omitted.append(f"outside repository: {raw}")
            continue
        available = path.is_file()
        references.append(
            {
                "path": str(path.relative_to(root)),
                "kind": "file",
                "available": available,
                "note": "" if available else "missing",
            }
        )
        if not available:
            omitted.append(str(path.relative_to(root)))
    return references, omitted


def _changed_files(repo_root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--short"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    return [line[3:] for line in result.stdout.splitlines() if len(line) > 3]


def _optional_string(arguments: Mapping[str, object], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _string_or_default(arguments: Mapping[str, object], key: str, default: str) -> str:
    value = arguments.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _bool_or_default(arguments: Mapping[str, object], key: str, default: bool) -> bool:
    value = arguments.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _loop_stop(arguments: Mapping[str, object]) -> str | None:
    value = arguments.get("loop_stop")
    if value is None or value is False:
        return None
    if value is True:
        return "critical-high"
    if isinstance(value, str) and value in {"critical-high", "none"}:
        return cast(ReviewLoopStop, value)
    raise ValueError("loop_stop must be a boolean, critical-high, or none")


def _resolved_loop_stop(value: object) -> ReviewLoopStop | None:
    if value is None:
        return None
    if isinstance(value, str) and value in {"critical-high", "none"}:
        return cast(ReviewLoopStop, value)
    raise ValueError("loop_stop must be critical-high or none")
