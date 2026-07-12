from __future__ import annotations

import argparse
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from quality_runner.application.review_projection import build_review_manifest
from quality_runner.application.review_v1_serializers import (
    review_manifest_to_v1,
    review_packet_to_v1,
    review_report_to_v1,
)
from quality_runner.artifacts import artifact_dir
from quality_runner.core.review_contracts import (
    AdapterStatus,
    EvidenceReference,
    ReviewPacket,
    ReviewReport,
)
from quality_runner.review_adapters import adapter_from_path
from quality_runner.review_artifacts import persist_review_artifacts
from quality_runner.review_context import build_review_context, normalize_review_options
from quality_runner.workflow_internal import generated_run_id

REVIEW_RESULT_SCHEMA = "quality-runner-review-result-v0.1"


def review_mcp_tool() -> dict[str, object]:
    return {
        "name": "quality_runner_review",
        "description": "Run a fresh local read-only review and write canonical artifacts.",
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
                "detail": {"enum": ["standard", "concise", "expanded"]},
                "save": {"type": "boolean"},
                "known_issues": {"type": "array", "items": {"type": "string"}},
                "loop": {"type": "boolean"},
                "loop_stop": {"type": "boolean"},
                "finding_id": {"type": "array", "items": {"type": "string"}},
                "all_critical_high": {"type": "boolean"},
                "adapter_output": {"type": "string"},
            },
            "required": ["repo_root"],
            "additionalProperties": False,
        },
    }


def review_mcp_payload(arguments: Mapping[str, object], repo_root: Path) -> dict[str, object]:
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
        loop_stop=_bool_or_default(arguments, "loop_stop", False),
        finding_id=strings("finding_id"),
        all_critical_high=_bool_or_default(arguments, "all_critical_high", False),
        adapter_output=_optional_string(arguments, "adapter_output"),
    )
    return review_command_payload(args, repo_root)


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
    parser.add_argument("--detail", choices=["standard", "concise", "expanded"], default="standard")
    parser.add_argument("--save", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--known-issues", action="append", default=[])
    parser.add_argument("--loop-stop", action="store_true")
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
        help="Render the additive v2 journey outcome instead of the legacy result projection",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def review_command_payload(args: argparse.Namespace, repo_root: Path) -> dict[str, object]:
    run_id = args.run_id or generated_run_id(suffix="review")
    task = _task_input(args)
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
    context = cast(
        ReviewPacket,
        build_review_context(
            repo_root=repo_root,
            run_id=run_id,
            options=options,
            repository_state={"detail": args.detail},
            changed_files=_changed_files(repo_root),
            omitted_evidence=omitted,
        ),
    )
    run_dir = artifact_dir(repo_root, run_id)
    adapter = adapter_from_path(Path(args.adapter_output) if args.adapter_output else None)
    result = adapter.review(context, run_dir)
    report = result["report"]
    if report is None:
        report = _empty_report(
            context,
            result["status"],
            result["evidence_unavailable"],
            result["message"],
        )
    manifest = build_review_manifest(
        context, artifact_paths=_expected_artifact_paths(repo_root, run_id) if args.save else {}
    )
    artifact_paths = persist_review_artifacts(
        repo_root=repo_root,
        run_id=run_id,
        manifest=review_manifest_to_v1(manifest),
        context=review_packet_to_v1(context),
        report=review_report_to_v1(report),
        save=args.save,
    )
    severity_counts = report["severity_counts"]
    next_action = result["message"]
    return {
        "schema": REVIEW_RESULT_SCHEMA,
        "status": result["status"],
        "run_id": run_id,
        "mode": context["mode"],
        "scope": context["scope"],
        "breadth": context["breadth"],
        "adapter_status": result["status"],
        "outcome": "packet-ready" if result["status"] == "review-not-run" else result["status"],
        "summary": report["summary"],
        "severity_counts": severity_counts,
        "evidence_unavailable": sorted(
            set(report["evidence_unavailable"] + result["evidence_unavailable"])
        ),
        "artifact_paths": artifact_paths,
        "saved_path": artifact_paths.get("review_report_json"),
        **({"next_action": next_action} if isinstance(next_action, str) and next_action else {}),
        "report": review_report_to_v1(report),
    }


def _task_input(args: argparse.Namespace) -> str | None:
    if args.task_file:
        return Path(args.task_file).expanduser().resolve().read_text(encoding="utf-8").strip()
    return args.task.strip() if isinstance(args.task, str) and args.task.strip() else None


def _evidence(repo_root: Path, paths: list[str]) -> tuple[list[EvidenceReference], list[str]]:
    references: list[EvidenceReference] = []
    omitted: list[str] = []
    root = repo_root.resolve()
    for raw in paths:
        path = (
            (root / raw).resolve()
            if not Path(raw).is_absolute()
            else Path(raw).expanduser().resolve()
        )
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


def _expected_artifact_paths(repo_root: Path, run_id: str) -> dict[str, str]:
    run_dir = artifact_dir(repo_root, run_id)
    return {
        "review_manifest_json": str(run_dir / "review-manifest.json"),
        "review_context_json": str(run_dir / "review-context.json"),
        "review_report_json": str(run_dir / "review-report.json"),
        "review_report_md": str(run_dir / "review-report.md"),
        "review_agent_packet_md": str(run_dir / "review-agent-packet.md"),
        "review_fix_prompts_md": str(run_dir / "review-fix-prompts.md"),
    }


def _empty_report(
    context: ReviewPacket,
    status: AdapterStatus,
    unavailable: Sequence[str],
    next_action: str | None,
) -> ReviewReport:
    from quality_runner.review_report import build_review_report

    mode = context["mode"]
    report = build_review_report(
        run_id=context["run_id"],
        mode=mode,
        scope=context["scope"],
        breadth=context["breadth"],
        findings=[],
        evidence_used=[],
        evidence_unavailable=[*unavailable, *context["omitted_evidence"]],
        exclusions=context["exclusions"],
        adapter_status=status,
        task_provenance=str(context["input_hashes"].get("task")) if mode != "blind" else None,
    )
    if next_action:
        report["next_action"] = next_action
    return report


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


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
