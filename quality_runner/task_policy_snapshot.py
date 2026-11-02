"""Apply task policy separately from the immutable source being measured."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from quality_runner.config import CONFIG_FILE_NAME
from quality_runner.task_snapshot_git import SnapshotError


def overlay_task_policy(repo_root: Path, snapshot_root: Path) -> None:
    source = repo_root / CONFIG_FILE_NAME
    target = snapshot_root / CONFIG_FILE_NAME
    if source.is_symlink() or (source.exists() and not source.is_file()):
        raise SnapshotError("task policy must be a regular file, not a symlink")
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise SnapshotError("snapshot policy must be a regular file, not a symlink")
    if source.is_file():
        shutil.copyfile(source, target)
    elif target.exists():
        target.unlink()


def rebaseline_source_ref(baseline: dict[str, Any], *, preserve_source: bool) -> str | None:
    source = baseline.get("source", {})
    head = source.get("head_sha")
    if not preserve_source:
        return head if source.get("kind") == "git_revision" and isinstance(head, str) else None
    if source.get("kind") not in {"workspace", "git_revision"} or not isinstance(head, str):
        raise SnapshotError("original source has no recoverable Git revision")
    return head


def verify_preserved_source(
    original: dict[str, Any], reconstructed: dict[str, Any]
) -> dict[str, Any]:
    if original.get("repository", {}).get("identity") != reconstructed["repository"]["identity"]:
        raise SnapshotError("original source belongs to a different Git repository")
    if (
        original.get("entries") != reconstructed["entries"]
        or original.get("snapshot_digest") != reconstructed["snapshot_digest"]
    ):
        raise SnapshotError(
            "original source cannot be recovered exactly from its recorded Git revision; "
            "preserve the existing baseline and recover its dirty or untracked source first"
        )
    # Retain workspace-versus-PR comparison semantics and the original provenance.
    # Only the analysis policy and its separately recorded contract are refreshed.
    return original
