from __future__ import annotations

import json
from pathlib import Path

from quality_runner.artifacts import write_json


def attach_review_metadata(
    *,
    repo_root: Path,
    run_id: str,
    cycle_id: str,
    iteration: int,
    baseline_run_id: str | None,
    delta_paths: dict[str, str],
) -> None:
    run_dir = repo_root / ".quality-runner" / "runs" / run_id
    manifest_path = run_dir / "run-manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["review_cycle"] = {
        "cycle_id": cycle_id,
        "iteration": iteration,
        "baseline_run_id": baseline_run_id,
        "artifact_paths": delta_paths,
    }
    write_json(manifest_path, manifest)
