from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_runner import __version__
from quality_runner.manifest import git_state_for_repo


def verification_provenance(
    *,
    repo_root: Path,
    run_id: str | None,
    gates: list[dict[str, Any]],
    verification_context: dict[str, Any] | None,
) -> dict[str, Any]:
    git = git_state_for_repo(repo_root)
    branch = git.get("branch")
    provenance: dict[str, Any] = {
        "head_sha": git.get("head_sha"),
        "branch": branch,
        "ref": _ref_for_branch(branch),
        "quality_runner_version": __version__,
        "captured_at": datetime.now(UTC).isoformat(),
        "worktree_mode": (
            verification_context.get("worktree_mode")
            if isinstance(verification_context, dict)
            else "in-place"
        ),
        "workflow_run_id": run_id,
    }
    digest = next(
        (
            gate.get("artifact_digest")
            for gate in gates
            if isinstance(gate, dict) and isinstance(gate.get("artifact_digest"), str)
        ),
        None,
    )
    if digest is not None:
        provenance["artifact_digest"] = digest
    return provenance


def artifact_digest(stdout: str, stderr: str) -> str | None:
    match = re.search(r"(?:sha256:)?([0-9a-fA-F]{64})", f"{stdout}\n{stderr}")
    return f"sha256:{match.group(1).lower()}" if match else None


def _ref_for_branch(branch: object) -> str | None:
    if not isinstance(branch, str) or not branch:
        return None
    return branch if branch.startswith("refs/") else f"refs/heads/{branch}"
