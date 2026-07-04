from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_release_smoke_runs_refresh_and_exports_handoff(tmp_path: Path) -> None:
    work_dir = tmp_path / "release-smoke"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "release-smoke",
            "--work-dir",
            str(work_dir),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    checks = {check["id"]: check for check in payload["checks"]}

    assert payload["schema"] == "quality-runner-release-smoke-result-v0.1"
    assert payload["status"] == "passed"
    assert checks["help"]["status"] == "passed"
    assert checks["doctor"]["status"] == "passed"
    assert checks["refresh_handoff"]["status"] == "passed"
    assert checks["export_handoff"]["status"] == "passed"
    assert checks["schema_compatibility"]["status"] == "passed"
    assert checks["compatibility_surfaces"]["status"] == "passed"
    assert (
        Path(payload["handoff_output"])
        .read_text(encoding="utf-8")
        .startswith("# Quality Runner Agent Handoff\n")
    )


def test_cli_release_smoke_human_summary_names_handoff(tmp_path: Path) -> None:
    work_dir = tmp_path / "release-smoke-human"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "release-smoke",
            "--work-dir",
            str(work_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "status: passed" in result.stdout
    assert "handoff:" in result.stdout
