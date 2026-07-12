from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from quality_runner.artifacts import validate_run_id
from repo_quality_certifier.core import (
    build_gate_matrix,
    build_gate_rollout_plan,
    build_rubric_pack,
    build_tmcp_expert_enrichment,
    gate_adoption_output_dir,
    scan_repo_gate_facts,
    write_adoption_doc_quality_report,
    write_gate_adoption_artifacts,
)

PLAN_RESULT_SCHEMA = "repo-quality-certifier-plan-result-v0.1"
DOC_QUALITY_RESULT_SCHEMA = "repo-quality-certifier-doc-quality-result-v0.1"


def _json_default(value: object) -> str:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _artifact_paths(paths: dict[str, Path]) -> dict[str, str]:
    return {key: str(path) for key, path in paths.items()}


def build_plan_payload(
    *,
    repo_root: Path,
    run_id: str,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.expanduser().resolve()
    validate_run_id(run_id)
    scan = scan_repo_gate_facts(repo_root, run_id=run_id)
    gate_matrix = build_gate_matrix(scan=scan, run_id=run_id)
    enrichment = build_tmcp_expert_enrichment(
        scan=scan,
        gate_matrix=gate_matrix,
        run_id=run_id,
    )
    rubric_pack = build_rubric_pack(
        scan=scan,
        gate_matrix=gate_matrix,
        run_id=run_id,
        tmcp_enrichment=enrichment,
    )
    rollout_plan = build_gate_rollout_plan(
        gate_matrix=gate_matrix,
        run_id=run_id,
        rubric_pack=rubric_pack,
    )
    artifact_dir = (
        output_dir.expanduser() if output_dir else gate_adoption_output_dir(repo_root, run_id)
    )
    paths = write_gate_adoption_artifacts(
        output_dir=artifact_dir,
        repo_root=repo_root,
        repo_scan=scan,
        gate_matrix=gate_matrix,
        rubric_pack=rubric_pack,
        rollout_plan=rollout_plan,
    )
    return {
        "schema": PLAN_RESULT_SCHEMA,
        "run_id": run_id,
        "status": "planned",
        "repo_root": str(repo_root),
        "artifact_paths": _artifact_paths(paths),
        "gate_summary": gate_matrix.get("summary", {}),
        "phase_scope_policy": rollout_plan.get("phase_scope_policy", ""),
        "phase_owner": rollout_plan.get("phase_owner", ""),
        "certifier_role": "standalone_quality_certification_engine",
        "repo_local_phases": rollout_plan.get("repo_local_phases", []),
        "rollout_phases": rollout_plan.get("phases", []),
    }


def build_doc_quality_payload(
    *,
    repo_root: Path,
    run_id: str,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    plan = build_plan_payload(repo_root=repo_root, run_id=run_id, output_dir=output_dir)
    manifest_path = plan["artifact_paths"].get("rubric_detail_manifest_json")
    artifact_dir = (
        Path(str(manifest_path)).parent
        if manifest_path
        else gate_adoption_output_dir(repo_root, run_id)
    )
    quality_paths = write_adoption_doc_quality_report(artifact_dir)
    quality_report = json.loads(
        quality_paths["adoption_doc_quality_json"].read_text(encoding="utf-8")
    )
    return {
        "schema": DOC_QUALITY_RESULT_SCHEMA,
        "run_id": run_id,
        "status": quality_report.get("status", "unknown"),
        "passed": quality_report.get("passed", False),
        "ready_for_phase_planning": quality_report.get("ready_for_phase_planning", False),
        "ready_for_execution": quality_report.get("ready_for_execution", False),
        "artifact_paths": {
            **plan["artifact_paths"],
            **_artifact_paths(quality_paths),
        },
        "gate_summary": plan["gate_summary"],
        "doc_quality": quality_report,
    }


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", required=True, help="Repository to certify")
    parser.add_argument(
        "--run-id",
        default=None,
        help="Stable run id for artifact paths; defaults to a generated id",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional artifact directory; defaults to AIOS-backfill/gate-adoption/{run_id}",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-quality-certifier",
        description="Generate repo quality certification evidence and rollout artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Generate certification plan artifacts")
    _add_common_args(plan_parser)

    doc_quality_parser = subparsers.add_parser(
        "doc-quality",
        help="Generate certification artifacts and validate generated document quality",
    )
    _add_common_args(doc_quality_parser)

    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.run_id or f"repo-quality-certifier-{uuid.uuid4().hex[:8]}"
    repo_root = Path(args.repo_root)
    output_dir = Path(args.output_dir) if args.output_dir else None
    if args.command == "plan":
        return build_plan_payload(repo_root=repo_root, run_id=run_id, output_dir=output_dir)
    if args.command == "doc-quality":
        return build_doc_quality_payload(repo_root=repo_root, run_id=run_id, output_dir=output_dir)
    raise ValueError(f"Unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = _run(args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
