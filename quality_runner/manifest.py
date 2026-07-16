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
    quality_skills: list[dict[str, Any]] | None = None,
    module_status: dict[str, Any] | None = None,
    worktree_mode: str = "in-place",
) -> dict[str, Any]:
# fmt: on
    created_at = datetime.now(UTC).isoformat()
    git = _git_state(repo_root)
    artifact_digests = _artifact_digests(artifact_paths)
    branch = git.get("branch")
    manifest: dict[str, Any] = {
        "schema": RUN_MANIFEST_SCHEMA,
        "run_id": run_id,
        "mode": mode,
        "repo_root": str(repo_root.expanduser().resolve()),
        "created_at": created_at,
        "quality_runner_version": __version__,
        "implementation_allowed": False,
        "git": git,
        "provenance": {
            "head_sha": git.get("head_sha"),
            "branch": git.get("branch"),
            "ref": (
                branch
                if isinstance(branch, str) and branch.startswith("refs/")
                else f"refs/heads/{branch}" if isinstance(branch, str) and branch and branch != "HEAD" else None
            ),
            "dirty": git.get("dirty"),
            "captured_at": created_at,
            "quality_runner_version": __version__,
            "worktree_mode": worktree_mode,
            "workflow_run_id": run_id,
        },
        "artifact_paths": artifact_paths,
    }
    if artifact_digests:
        manifest["artifact_digests"] = artifact_digests
    if intent is not None:
        manifest["intent"] = intent
    if quality_skills:
        manifest["quality_skills"] = quality_skills
    if module_status is not None:
        manifest["module_status"] = module_status
    return manifest


def git_state_for_repo(repo_root: Path) -> dict[str, Any]:
    return _git_state(repo_root)


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


def _artifact_digests(artifact_paths: dict[str, str]) -> dict[str, str]:
    import hashlib

    digests: dict[str, str] = {}
    for key, value in artifact_paths.items():
        path = Path(value)
        if not path.is_file() or path.is_symlink():
            continue
        try:
            digests[key] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
        except OSError:
            continue
    return digests
