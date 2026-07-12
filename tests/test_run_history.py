from __future__ import annotations

import os
from pathlib import Path

import pytest

from quality_runner.application.run_history import load_run_history
from quality_runner.workflow import run_payload


def test_run_history_reads_summaries_without_persisting_new_artifacts(tmp_path: Path) -> None:
    run_payload(repo_root=tmp_path, run_id="history-a")
    run_payload(repo_root=tmp_path, run_id="history-b")

    history = load_run_history(repo_root=tmp_path, limit=20)

    assert [run["run_id"] for run in history["runs"]] == ["history-b", "history-a"]
    assert history["truncated"] is False
    assert history["unavailable_run_ids"] == []
    assert not (tmp_path / ".quality-runner" / "runs" / "history-a" / "run-summary.json").exists()
    assert not (tmp_path / ".quality-runner" / "runs" / "history-b" / "run-summary.json").exists()


def test_run_history_reads_a_selected_run_without_persisting(tmp_path: Path) -> None:
    run_payload(repo_root=tmp_path, run_id="history-selected")

    history = load_run_history(repo_root=tmp_path, run_id="history-selected")

    assert history["selected_run_id"] == "history-selected"
    assert [run["run_id"] for run in history["runs"]] == ["history-selected"]
    assert not (
        tmp_path / ".quality-runner" / "runs" / "history-selected" / "run-summary.json"
    ).exists()


def test_run_history_surfaces_an_unreadable_selected_run_without_writing(tmp_path: Path) -> None:
    history = load_run_history(repo_root=tmp_path, run_id="missing-run")

    assert history["runs"] == []
    assert history["selected_run_id"] == "missing-run"
    assert history["unavailable_run_ids"] == ["missing-run"]


def test_run_history_rejects_unsafe_selected_run_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="single path segment"):
        load_run_history(repo_root=tmp_path, run_id="../escape")


def test_run_history_marks_unsafe_artifacts_unavailable(tmp_path: Path) -> None:
    run_payload(repo_root=tmp_path, run_id="unsafe-artifact")
    run_dir = tmp_path / ".quality-runner" / "runs" / "unsafe-artifact"
    target = tmp_path / "outside.json"
    target.write_text("{}", encoding="utf-8")
    (run_dir / "quality-audit.json").unlink()
    os.symlink(target, run_dir / "quality-audit.json")

    history = load_run_history(repo_root=tmp_path, run_id="unsafe-artifact")

    assert history["runs"] == []
    assert history["unavailable_run_ids"] == ["unsafe-artifact"]


@pytest.mark.parametrize("limit", [0, 101])
def test_run_history_rejects_unbounded_limits(tmp_path: Path, limit: int) -> None:
    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        load_run_history(repo_root=tmp_path, limit=limit)
