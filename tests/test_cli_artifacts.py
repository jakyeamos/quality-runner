from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_prune_artifacts_defaults_to_preview_and_applies_policy(tmp_path: Path) -> None:
    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner.artifacts]\nretention_runs = 1\n",
        encoding="utf-8",
    )
    runs_dir = tmp_path / ".quality-runner" / "runs"
    (runs_dir / "old").mkdir(parents=True)
    (runs_dir / "new").mkdir()
    os.utime(runs_dir / "old", (100, 100))
    os.utime(runs_dir / "new", (200, 200))

    preview = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "prune-artifacts",
            str(tmp_path),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    preview_payload = json.loads(preview.stdout)
    assert preview_payload["apply"] is False
    assert preview_payload["would_delete_run_ids"] == ["old"]
    assert (runs_dir / "old").exists()

    applied = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "prune-artifacts",
            str(tmp_path),
            "--apply",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    applied_payload = json.loads(applied.stdout)
    assert applied_payload["status"] == "pruned"
    assert applied_payload["deleted_run_ids"] == ["old"]
    assert not (runs_dir / "old").exists()
