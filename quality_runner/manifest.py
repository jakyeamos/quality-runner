from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner import __version__
from quality_runner.schema_constants import RUN_MANIFEST_SCHEMA


# fmt: off
def build_run_manifest(
    *,
    repo_root: Path,
    run_id: str,
    mode: str,
    artifact_paths: dict[str, str],
    intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
# fmt: on
    manifest: dict[str, Any] = {
        "schema": RUN_MANIFEST_SCHEMA,
        "run_id": run_id,
        "mode": mode,
        "repo_root": str(repo_root.expanduser().resolve()),
        "created_at": datetime.now(UTC).isoformat(),
        "quality_runner_version": __version__,
        "implementation_allowed": False,
        "git": _git_state(repo_root),
        "artifact_paths": artifact_paths,
    }
    if intent is not None:
        manifest["intent"] = intent
    return manifest


def _git_state(repo_root: Path) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    if not (root / ".git").exists():
        return _no_git_state()

    head_sha = _git_output(root, "rev-parse", "HEAD")
    branch = _git_output(root, "rev-parse", "--abbrev-ref", "HEAD")
    status = _git_output(root, "status", "--porcelain")
    return {
        "is_repo": head_sha is not None,
        "head_sha": head_sha,
        "branch": branch,
        "dirty": None if status is None else bool(status),
    }


def _no_git_state() -> dict[str, Any]:
    return {"is_repo": False, "head_sha": None, "branch": None, "dirty": None}


def _git_output(repo_root: Path, *args: str) -> str | None:
    try:
        # fmt: off
        result = subprocess.run(
            ["git", *args], cwd=repo_root, check=False, capture_output=True, text=True, timeout=5,
        )
        # fmt: on
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None
