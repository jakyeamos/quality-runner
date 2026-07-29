from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from quality_runner.task_snapshot import (
    SnapshotError,
    attach_git_metadata,
    changed_paths,
    workspace_snapshot,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "quality-runner@example.com")
    _git(tmp_path, "config", "user.name", "Quality Runner")
    (tmp_path / "tracked.txt").write_text("before\n", encoding="utf-8")
    (tmp_path / "delete.txt").write_text("delete\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "fixture")
    return tmp_path


def test_workspace_snapshot_captures_edits_deletions_and_untracked_files(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "tracked.txt").write_text("after\n", encoding="utf-8")
    (repo / "delete.txt").unlink()
    (repo / "untracked.txt").write_text("new\n", encoding="utf-8")

    with workspace_snapshot(repo) as (snapshot, manifest):
        assert (snapshot / "tracked.txt").read_text() == "after\n"
        assert (snapshot / "untracked.txt").read_text() == "new\n"
        assert not (snapshot / "delete.txt").exists()
        entries = {item["path"]: item for item in manifest["entries"]}

    assert entries["delete.txt"]["kind"] == "deleted"
    assert entries["tracked.txt"]["kind"] == "file"
    assert entries["untracked.txt"]["kind"] == "file"


def test_revision_snapshot_is_not_replaced_by_dirty_head(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    baseline_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")

    with workspace_snapshot(repo, baseline_ref=baseline_sha) as (snapshot, manifest):
        assert (snapshot / "tracked.txt").read_text() == "before\n"
        assert manifest["source"]["kind"] == "git_revision"
        assert manifest["source"]["head_sha"] == baseline_sha


def test_snapshot_records_default_exclusions_and_allows_explicit_include(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    dependency = repo / "node_modules" / "fixture.txt"
    dependency.parent.mkdir()
    dependency.write_text("dependency\n", encoding="utf-8")
    _git(repo, "add", "-f", "node_modules/fixture.txt")
    _git(repo, "commit", "-m", "tracked dependency")

    with workspace_snapshot(repo) as (snapshot, manifest):
        assert not (snapshot / "node_modules" / "fixture.txt").exists()
        assert {(item["path"], item["reason"]) for item in manifest["exclusions"]} >= {
            ("node_modules/fixture.txt", "dependency")
        }

    with workspace_snapshot(repo, include_paths=("node_modules/**",)) as (snapshot, _manifest):
        assert (snapshot / "node_modules" / "fixture.txt").read_text() == "dependency\n"


def test_snapshot_hashes_safe_symlink_and_blocks_escaping_symlink(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    os.symlink("tracked.txt", repo / "safe-link")
    _git(repo, "add", "safe-link")
    _git(repo, "commit", "-m", "safe link")

    with workspace_snapshot(repo) as (snapshot, manifest):
        assert (snapshot / "safe-link").is_symlink()
        link = next(item for item in manifest["entries"] if item["path"] == "safe-link")
        assert link["target"] == "tracked.txt"

    (repo / "safe-link").unlink()
    os.symlink("../outside", repo / "safe-link")
    with pytest.raises(SnapshotError, match="escapes"):
        with workspace_snapshot(repo):
            pass


def test_snapshot_fails_closed_when_tracked_file_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)
    original = Path.read_bytes

    def fail_for_tracked(path: Path) -> bytes:
        if path.name == "tracked.txt":
            raise PermissionError("fixture unreadable")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", fail_for_tracked)
    with pytest.raises(SnapshotError, match="unreadable workspace entry"):
        with workspace_snapshot(repo):
            pass


def test_changed_paths_compares_manifest_content_and_deletions() -> None:
    baseline = {
        "entries": [
            {"path": "a.py", "kind": "file", "sha256": "old"},
            {"path": "gone.py", "kind": "file", "sha256": "same"},
        ]
    }
    current = {
        "entries": [
            {"path": "a.py", "kind": "file", "sha256": "new"},
            {"path": "new.py", "kind": "file", "sha256": "same"},
        ]
    }

    assert changed_paths(baseline, current) == ["a.py", "gone.py", "new.py"]


def test_gate_snapshot_has_git_history_without_replacing_dirty_files(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("new\n", encoding="utf-8")

    with workspace_snapshot(repo) as (snapshot, _manifest):
        attach_git_metadata(repo, snapshot)
        assert (
            subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=snapshot,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            == subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        assert (snapshot / "tracked.txt").read_text() == "dirty\n"
        assert (snapshot / "untracked.txt").read_text() == "new\n"
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=snapshot,
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    assert " M tracked.txt" in status
    assert "?? untracked.txt" in status
