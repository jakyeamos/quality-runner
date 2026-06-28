from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from test_support.quality_runner_fixtures import write_js_fixture

ROOT = Path(__file__).resolve().parents[1]


def test_cli_run_json_writes_artifacts(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "run",
            str(tmp_path),
            "--run-id",
            "cli-run",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-run-result-v0.1"
    assert payload["status"] == "planned"
    assert payload["run_id"] == "cli-run"
    assert payload["implementation_allowed"] is False
    assert Path(payload["artifact_paths"]["agent_handoff_md"]).exists()


def test_cli_inspect_json_writes_inspection_artifacts(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "inspect",
            str(tmp_path),
            "--run-id",
            "cli-inspect",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-inspect-result-v0.1"
    assert payload["status"] == "inspected"
    assert payload["run_id"] == "cli-inspect"
    assert Path(payload["artifact_paths"]["repo_scan_json"]).exists()
    assert "quality_audit_json" not in payload["artifact_paths"]


def test_cli_doctor_json_reports_ready() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "doctor", "--json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "quality-runner-doctor-result-v0.1"
    assert payload["status"] == "ready"
    assert payload["version"] == "0.1.0"
    assert payload["environment"]["python_executable"]


def test_cli_invalid_repo_path_fails_without_traceback(tmp_path: Path) -> None:
    missing_repo = tmp_path / "missing"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "run",
            str(missing_repo),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "repo root does not exist" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


def test_cli_version_preserves_bare_version_output() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "0.1.0"
