from __future__ import annotations

import subprocess
from pathlib import Path

from quality_runner.read_only_git import restore_if_changed, tracked_snapshot


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_read_only_snapshot_reports_untracked_mutation_without_deleting_it(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Quality Runner Test")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-qm", "fixture")

    before = tracked_snapshot(tmp_path)
    untracked = tmp_path / "gate-output.txt"
    untracked.write_text("created by gate\n", encoding="utf-8")
    mutation = restore_if_changed(tmp_path, before)

    assert mutation is not None
    assert "gate-output.txt" in mutation["untracked_or_ignored_files"]
    assert untracked.exists()
    assert mutation["restored"] is False


def test_read_only_snapshot_allows_qr_owned_artifacts(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Quality Runner Test")
    (tmp_path / "tracked.txt").write_text("fixture\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-qm", "fixture")

    before = tracked_snapshot(tmp_path)
    artifact = tmp_path / ".quality-runner" / "runs" / "run-1" / "gate.log"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("allowed\n", encoding="utf-8")

    assert restore_if_changed(tmp_path, before) is None


def test_read_only_snapshot_hashes_files_inside_ignored_directories(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Quality Runner Test")
    (tmp_path / ".gitignore").write_text("ignored-cache/\n", encoding="utf-8")
    _git(tmp_path, "add", ".gitignore")
    _git(tmp_path, "commit", "-qm", "fixture")

    before = tracked_snapshot(tmp_path)
    ignored = tmp_path / "ignored-cache" / "evidence.json"
    ignored.parent.mkdir()
    ignored.write_text("before\n", encoding="utf-8")
    after_creation = restore_if_changed(tmp_path, before)

    assert after_creation is not None
    assert "ignored-cache/evidence.json" in after_creation["untracked_or_ignored_files"]
    assert ignored.exists()


def test_read_only_snapshot_skips_dependency_and_cache_trees(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Quality Runner Test")
    (tmp_path / ".gitignore").write_text("node_modules/\n.next/\n", encoding="utf-8")
    _git(tmp_path, "add", ".gitignore")
    _git(tmp_path, "commit", "-qm", "fixture")

    dependency = tmp_path / "node_modules" / "package" / "index.js"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("before\n", encoding="utf-8")
    cache = tmp_path / ".next" / "cache.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("before\n", encoding="utf-8")

    before = tracked_snapshot(tmp_path)

    assert all("node_modules" not in path for path in before.ignored_files)
    assert all(".next" not in path for path in before.ignored_files)

    dependency.write_text("after\n", encoding="utf-8")
    cache.write_text("after\n", encoding="utf-8")

    assert restore_if_changed(tmp_path, before) is None
