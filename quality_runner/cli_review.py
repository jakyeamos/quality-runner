from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import cast

from quality_runner.artifacts import artifact_dir
from quality_runner.review_adapters import adapter_from_path
from quality_runner.review_artifacts import persist_review_artifacts
from quality_runner.review_context import build_review_context, normalize_review_options
from quality_runner.review_types import EvidenceReference, ReviewOptions
from quality_runner.workflow_internal import generated_run_id

REVIEW_RESULT_SCHEMA = "quality-runner-review-result-v0.1"


def add_review_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("review", help="Run a fresh, read-only review")
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument("--run-id", default=None, help="Stable review run id")
    parser.add_argument("--mode", choices=["task", "blind", "combined"], default="task")
    parser.add_argument("--scope", choices=["task", "project"], default="project")
    parser.add_argument("--breadth", choices=["focused", "related", "full"], default=None)
    parser.add_argument("--task", default=None, help="Task or acceptance criteria under review")
    parser.add_argument("--task-file", default=None, help="Read task text from a local file")
    parser.add_argument("--reuse-task", action="store_true", help="Reuse --previous-summary as task context")
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
    parser.add_argument("--adapter-output", default=None, help="Local adapter result JSON inside the run artifact directory")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def review_command_payload(args: argparse.Namespace, repo_root: Path) -> dict[str, object]:
    run_id = args.run_id or generated_run_id(suffix="review")
    task = _task_input(args)
    if args.reuse_task and not task:
        task = args.previous_summary
    if args.mode in {"task", "combined"} and not task:
        raise ValueError("task mode requires --task or --task-file; use --mode blind for a fresh blind review")
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
    context = build_review_context(
        repo_root=repo_root,
        run_id=run_id,
        options=options,
        repository_state={"detail": args.detail},
        changed_files=_changed_files(repo_root),
        omitted_evidence=omitted,
    )
    run_dir = artifact_dir(repo_root, run_id)
    adapter = adapter_from_path(Path(args.adapter_output) if args.adapter_output else None)
    result = adapter.review(context, run_dir)
    report = result["report"] or _empty_report(context, result["status"], result["evidence_unavailable"])
    manifest = _manifest(context, artifact_paths=_expected_artifact_paths(repo_root, run_id) if args.save else {})
    artifact_paths = persist_review_artifacts(
        repo_root=repo_root,
        run_id=run_id,
        manifest=manifest,
        context=context,
        report=report,
        save=args.save,
    )
    severity_counts = report.get("severity_counts", {})
    return {
        "schema": REVIEW_RESULT_SCHEMA,
        "status": result["status"],
        "run_id": run_id,
        "mode": context["mode"],
        "scope": context["scope"],
        "breadth": context["breadth"],
        "adapter_status": result["status"],
        "summary": report["summary"],
        "severity_counts": severity_counts,
        "evidence_unavailable": sorted(set(_strings(report.get("evidence_unavailable")) + result["evidence_unavailable"])),
        "artifact_paths": artifact_paths,
        "saved_path": artifact_paths.get("review_report_json"),
        "report": report,
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
        path = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw).expanduser().resolve()
        try:
            path.relative_to(root)
        except ValueError:
            omitted.append(f"outside repository: {raw}")
            continue
        available = path.is_file()
        references.append({"path": str(path.relative_to(root)), "kind": "file", "available": available, "note": "" if available else "missing"})
        if not available:
            omitted.append(str(path.relative_to(root)))
    return references, omitted


def _changed_files(repo_root: Path) -> list[str]:
    try:
        result = subprocess.run(["git", "-C", str(repo_root), "status", "--short"], capture_output=True, text=True, check=False)
    except OSError:
        return []
    return [line[3:] for line in result.stdout.splitlines() if len(line) > 3]


def _manifest(context: dict[str, object], *, artifact_paths: dict[str, str]) -> dict[str, object]:
    return {
        "schema": "quality-runner-review-manifest-v0.1",
        "run_id": context["run_id"],
        "mode": context["mode"],
        "scope": context["scope"],
        "breadth": context["breadth"],
        "exclusions": context.get("exclusions", []),
        "evidence_references": context.get("evidence", []),
        "freshness": context["freshness"],
        "input_hashes": context["input_hashes"],
        "artifact_paths": artifact_paths,
    }


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


def _empty_report(context: dict[str, object], status: str, unavailable: list[str]) -> dict[str, object]:
    from quality_runner.review_report import build_review_report

    mode = cast(str, context["mode"])
    return build_review_report(
        run_id=str(context["run_id"]), mode=mode, scope=str(context["scope"]), breadth=str(context["breadth"]),
        findings=[], evidence_used=[], evidence_unavailable=unavailable + _strings(context.get("omitted_evidence")),
        exclusions=_strings(context.get("exclusions")), adapter_status=status,
        task_provenance=str(context.get("input_hashes", {}).get("task")) if mode != "blind" else None,
    )


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
