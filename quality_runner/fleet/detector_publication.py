from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from quality_runner.artifacts import prepare_safe_directory, write_json


def publish_detector_runs(
    *,
    worktree: Path,
    publication_root: Path,
    run_ids: list[str],
    target_branch: str,
    target_head: str,
    detector_provenance: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Copy validated detector runs and bind them to the published target."""
    source_runs = worktree / ".quality-runner" / "runs"
    destination_runs = publication_root / ".quality-runner" / "runs"
    prepare_safe_directory(destination_runs)
    publications: list[tuple[Path, Path]] = []
    for run_id in run_ids:
        source = source_runs / run_id
        destination = destination_runs / run_id
        if not source.is_dir() or source.is_symlink():
            raise ValueError(f"refresh did not produce expected run: {run_id}")
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"publication destination already exists: {destination}")
        if any(path.is_symlink() for path in source.rglob("*")):
            raise ValueError(f"refusing to publish a run containing symlinks: {run_id}")
        publications.append((source, destination))
    published: list[Path] = []
    try:
        for source, destination in publications:
            shutil.copytree(source, destination)
            published.append(destination)
            _rewrite_published_json(
                destination,
                worktree=worktree,
                publication_root=publication_root,
                target_branch=target_branch,
                target_head=target_head,
                detector_provenance=detector_provenance or [],
            )
    except (OSError, ValueError, json.JSONDecodeError):
        for destination in published:
            shutil.rmtree(destination, ignore_errors=True)
        raise
    return [str(destination) for destination in published]


def _rewrite_published_json(
    run_dir: Path,
    *,
    worktree: Path,
    publication_root: Path,
    target_branch: str,
    target_head: str,
    detector_provenance: list[dict[str, Any]],
) -> None:
    for path in run_dir.rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        text = text.replace(str(worktree), str(publication_root))
        text = text.replace('"branch": "HEAD"', f'"branch": {json.dumps(target_branch)}')
        text = text.replace(
            '"ref": "refs/heads/HEAD"', f'"ref": {json.dumps(f"refs/heads/{target_branch}")}'
        )
        path.write_text(text, encoding="utf-8")
    provenance = {
        "schema": "quality-runner-fleet-detector-publication/v1",
        "target_branch": target_branch,
        "target_head": target_head,
        "analysis_mode": "full",
        "skill_packs": "enabled",
        "detectors": detector_provenance,
    }
    write_json(run_dir / "fleet-detector-publication.json", provenance)
