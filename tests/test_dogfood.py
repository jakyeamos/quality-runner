from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from quality_runner.dogfood import dogfood_report, record_task_event

ROOT = Path(__file__).resolve().parents[1]


def _check_payload() -> dict[str, object]:
    return {
        "status": "pass",
        "mode": "authoritative",
        "release_enforcement": "required",
        "run_id": "run-1",
        "repository": {"identity": "repository-secret", "root": "/private/repository"},
        "changed_paths": ["private/source.py"],
        "delta": {"counts": {"new_enforced": 0, "persisted": 2, "resolved": 1, "unknown": 0}},
        "gate_results": [{"id": "tests", "status": "passed"}],
        "release_readiness": {"eligible": True},
        "analysis": {
            "performance": {"elapsed_seconds": 2.5},
            "cache_summary": {"analyses": {"code_quality": {"cache_hits": 4, "cache_misses": 1}}},
        },
    }


def test_capture_is_idempotent_private_and_reportable(tmp_path: Path) -> None:
    payload = _check_payload()
    first = record_task_event(
        repo_root=tmp_path,
        task_id="private-task-name",
        action="release_check",
        payload=payload,
        operation_seconds=3.0,
        state_dir=tmp_path / "state",
    )
    second = record_task_event(
        repo_root=tmp_path,
        task_id="private-task-name",
        action="release_check",
        payload=payload,
        operation_seconds=3.0,
        state_dir=tmp_path / "state",
    )
    report = dogfood_report(tmp_path / "state")

    assert first["status"] == "recorded"
    assert second["status"] == "duplicate"
    assert report["coverage"] == {
        "events": 1,
        "tasks": 1,
        "repositories": 1,
        "event_counts": {"quality_runner.task.release.check": 1},
        "status_counts": {"pass": 1},
    }
    assert report["feedback_loop"]["release_eligibility_rate"] == 1.0
    assert report["feedback_loop"]["resolved_findings"] == 1
    database_bytes = (tmp_path / "state" / "events.sqlite3").read_bytes()
    assert b"private-task-name" not in database_bytes
    assert b"private/source.py" not in database_bytes
    assert b"/private/repository" not in database_bytes


def test_empty_report_has_explicit_coverage_and_privacy(tmp_path: Path) -> None:
    report = dogfood_report(tmp_path / "missing")

    assert report["status"] == "empty"
    assert report["coverage"]["events"] == 0
    assert report["privacy"]["raw_prompts"] is False
    assert report["privacy"]["source_paths"] is False


def test_capture_failure_is_visible_but_does_not_replace_task_result(tmp_path: Path) -> None:
    state_file = tmp_path / "not-a-directory"
    state_file.write_text("occupied", encoding="utf-8")

    capture = record_task_event(
        repo_root=tmp_path,
        task_id="task",
        action="start",
        payload={"status": "started"},
        operation_seconds=0.1,
        state_dir=state_file,
    )

    assert capture["status"] == "degraded"
    assert capture["error"]["code"] == "dogfood_capture_unavailable"
    assert "task" not in json.dumps(capture)


def test_report_cli_reads_the_configured_local_store(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "dogfood", "report", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "QUALITY_RUNNER_DOGFOOD_STATE_DIR": str(tmp_path / "state")},
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "empty"
