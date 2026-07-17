from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from quality_runner.findings import validate_agent_handoff
from quality_runner.handoff_lint import validate_handoff_quality, validate_slice_spec_content
from quality_runner.remediation_context import validate_remediation_context
from quality_runner.review_worker import review_worker_payload
from quality_runner.slice_specs import export_slice_specs_payload


def add_handoff_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    export_slice_specs = subparsers.add_parser(
        "export-slice-specs",
        help="Write improve-style cold-executor slice specs for a run",
    )
    export_slice_specs.add_argument("repo_path", help="Target repository path")
    export_slice_specs.add_argument("--run-id", required=True, help="Run id to export")
    export_slice_specs.add_argument("--json", action="store_true", help="Emit JSON output")

    validate_handoff = subparsers.add_parser(
        "validate-handoff",
        help="Validate agent handoff schema and executor-readiness checks",
    )
    validate_handoff.add_argument("handoff_json", help="Agent handoff JSON path")
    validate_handoff.add_argument(
        "--remediation-plan",
        default=None,
        help="Optional remediation plan JSON for slice-level lint",
    )
    validate_handoff.add_argument(
        "--remediation-context",
        default=None,
        help="Completed remediation context JSON to use for understanding validation",
    )
    validate_handoff.add_argument("--json", action="store_true", help="Emit JSON output")

    validate_context = subparsers.add_parser(
        "validate-remediation-context",
        help="Validate a compact remediation context packet before source changes",
    )
    validate_context.add_argument("context_json", help="Remediation context JSON path")
    validate_context.add_argument(
        "--remediation-plan",
        default=None,
        help="Optional remediation plan JSON for slice coverage validation",
    )
    validate_context.add_argument("--json", action="store_true", help="Emit JSON output")

    validate_slice_spec = subparsers.add_parser(
        "validate-slice-spec",
        help="Validate a generated slice spec markdown file",
    )
    validate_slice_spec.add_argument("slice_spec_path", help="Slice spec markdown path")
    validate_slice_spec.add_argument("--json", action="store_true", help="Emit JSON output")

    review_worker = subparsers.add_parser(
        "review-worker",
        help="Verify a worker report against baseline and final QR runs",
    )
    review_worker.add_argument("repo_path", help="Target repository path")
    review_worker.add_argument("--baseline-run-id", required=True, help="Baseline QR run id")
    review_worker.add_argument("--final-run-id", required=True, help="Final QR run id")
    review_worker.add_argument(
        "--worker-report",
        required=True,
        help="Controller/worker completion report JSON path",
    )
    review_worker.add_argument("--json", action="store_true", help="Emit JSON output")


def handoff_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "export-slice-specs":
        return export_slice_specs_payload(
            repo_root=Path(args.repo_path).expanduser().resolve(),
            run_id=args.run_id,
        )
    if args.command == "validate-handoff":
        return validate_handoff_command_payload(args)
    if args.command == "validate-remediation-context":
        return validate_remediation_context_command_payload(args)
    if args.command == "validate-slice-spec":
        return validate_slice_spec_command_payload(args)
    if args.command == "review-worker":
        return review_worker_payload(
            repo_root=Path(args.repo_path).expanduser().resolve(),
            baseline_run_id=args.baseline_run_id,
            final_run_id=args.final_run_id,
            worker_report_path=Path(args.worker_report).expanduser().resolve(),
        )
    raise ValueError(f"unsupported handoff command: {args.command}")


def validate_handoff_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    handoff_path = Path(args.handoff_json).expanduser().resolve()
    handoff = _load_json(handoff_path)
    schema_result = validate_agent_handoff(handoff)
    plan = None
    if args.remediation_plan:
        plan = _load_json(Path(args.remediation_plan).expanduser().resolve())
    context = None
    if args.remediation_context:
        context = _load_json(Path(args.remediation_context).expanduser().resolve())
    quality_result = validate_handoff_quality(
        handoff,
        remediation_plan=plan,
        remediation_context=context,
    )
    errors = [*schema_result.get("errors", []), *quality_result.get("errors", [])]
    return {
        "schema": "quality-runner-validate-handoff-result-v0.1",
        "status": "passed" if not errors else "rejected",
        "implementation_allowed": False,
        "schema_validation": schema_result,
        "quality_validation": quality_result,
        "errors": errors,
    }


def validate_remediation_context_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    context = _load_json(Path(args.context_json).expanduser().resolve())
    plan = None
    if args.remediation_plan:
        plan = _load_json(Path(args.remediation_plan).expanduser().resolve())
    result = validate_remediation_context(context, remediation_plan=plan, require_ready=True)
    return {
        "schema": "quality-runner-validate-remediation-context-result-v0.1",
        "status": "passed" if result.get("passed") else "rejected",
        "implementation_allowed": False,
        **result,
    }


def validate_slice_spec_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.slice_spec_path).expanduser().resolve()
    result = validate_slice_spec_content(path.read_text(encoding="utf-8"))
    return {
        "schema": "quality-runner-validate-slice-spec-result-v0.1",
        "status": "passed" if result.get("passed") else "rejected",
        "implementation_allowed": False,
        "path": str(path),
        **result,
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object required: {path}")
    return payload
