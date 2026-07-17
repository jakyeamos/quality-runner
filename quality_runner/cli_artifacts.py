from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from quality_runner.artifacts import cleanup_artifacts

PRUNE_ARTIFACTS_RESULT_SCHEMA = "quality-runner-prune-artifacts-result-v0.1"


def add_artifact_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "prune-artifacts",
        help="Preview or delete persisted Quality Runner runs using repo retention policy",
    )
    parser.add_argument("repo_path", help="Target repository path")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete runs selected by retention policy; default is a dry run",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def prune_artifacts_payload(*, repo_root: Path, apply: bool) -> dict[str, Any]:
    result = cleanup_artifacts(repo_root, apply=apply)
    return {
        "schema": PRUNE_ARTIFACTS_RESULT_SCHEMA,
        "status": result["status"],
        "repo_root": str(repo_root),
        "implementation_allowed": False,
        "apply": apply,
        "retention_runs": result["retention_runs"],
        "retention_days": result["retention_days"],
        "deleted_run_ids": result["deleted_run_ids"],
        "would_delete_run_ids": result["would_delete_run_ids"],
        "preserved_run_ids": result["preserved_run_ids"],
        "skipped_entries": result["skipped_entries"],
    }
