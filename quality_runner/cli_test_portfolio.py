"""CLI routing for test-portfolio review and removal-proof evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.artifacts import artifact_dir, prepare_artifact_dir, write_json
from quality_runner.manifest import build_run_manifest, git_state_for_repo
from quality_runner.test_portfolio import (
    audit_test_portfolio,
    build_test_removal_proof,
    load_test_portfolio_json,
    write_test_portfolio_json,
)


def add_test_portfolio_commands(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "tests",
        help="Review test value and validate exact-revision removal evidence",
    )
    actions = parser.add_subparsers(dest="tests_action", required=True)
    for action, help_text in (
        ("portfolio-audit", "Classify caller-assembled test value evidence"),
        ("removal-proof", "Fail closed on test-removal evidence gaps"),
    ):
        action_parser = actions.add_parser(action, help=help_text)
        action_parser.add_argument("repo_path", help="Repository receiving the QR run")
        action_parser.add_argument("manifest_path", help="Input manifest JSON")
        action_parser.add_argument("--run-id", required=True, help="Stable QR run id")
        action_parser.add_argument(
            "--output", default=None, help="Optionally export a second artifact copy"
        )
        action_parser.add_argument("--json", action="store_true", help="Emit JSON output")


def test_portfolio_command_payload(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_path).expanduser().resolve()
    if not repo_root.is_dir():
        raise ValueError(f"repository directory does not exist: {repo_root}")
    manifest_path = Path(args.manifest_path).expanduser().resolve()
    manifest = load_test_portfolio_json(manifest_path)
    if args.tests_action == "portfolio-audit":
        artifact = audit_test_portfolio(manifest)
    elif args.tests_action == "removal-proof":
        artifact = build_test_removal_proof(manifest)
    else:
        raise ValueError(f"unsupported tests action: {args.tests_action}")
    git_state = git_state_for_repo(repo_root)
    _validate_live_provenance(artifact, git_state=git_state, action=args.tests_action)

    run_dir = artifact_dir(repo_root, args.run_id)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError(f"QR run id already contains artifacts: {args.run_id}")
    run_dir = prepare_artifact_dir(repo_root, args.run_id)
    filename = (
        "test-portfolio-audit.json"
        if args.tests_action == "portfolio-audit"
        else "test-removal-proof.json"
    )
    artifact_key = (
        "test_portfolio_audit_json"
        if args.tests_action == "portfolio-audit"
        else "test_removal_proof_json"
    )
    artifact_path = run_dir / filename
    artifact_paths = {
        artifact_key: str(artifact_path),
        "run_manifest_json": str(run_dir / "run-manifest.json"),
    }
    run_manifest = build_run_manifest(
        repo_root=repo_root,
        run_id=args.run_id,
        mode=f"test-{args.tests_action}",
        artifact_paths=artifact_paths,
    )
    artifact_path = write_json(artifact_path, artifact)
    manifest_output_path = write_json(run_dir / "run-manifest.json", run_manifest)
    export_output_path = (
        write_test_portfolio_json(Path(args.output), artifact) if args.output else None
    )
    return {
        **artifact,
        "operation": args.tests_action,
        "repo_root": str(repo_root),
        "run_id": args.run_id,
        "input_path": str(manifest_path),
        "output_path": str(artifact_path),
        "export_output_path": str(export_output_path) if export_output_path else None,
        "artifact_paths": {**artifact_paths, "run_manifest_json": str(manifest_output_path)},
    }


def _validate_live_provenance(
    artifact: dict[str, Any], *, git_state: dict[str, Any], action: str
) -> None:
    if git_state.get("is_repo") is not True:
        raise ValueError("test-portfolio command runs require a Git repository")
    live_head = git_state.get("head_sha")
    revision = artifact.get("revision")
    artifact_head = revision.get("head") if isinstance(revision, dict) else None
    if not isinstance(live_head, str) or artifact_head != live_head:
        raise ValueError(
            "artifact revision.head must match the receiving repository HEAD "
            f"({artifact_head!r} != {live_head!r})"
        )
    if action == "removal-proof" and git_state.get("dirty") is not False:
        raise ValueError("removal-proof command runs require a clean receiving repository")
