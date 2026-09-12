from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from quality_runner.task_snapshot import _repository_identity


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Identity fixture")
    _git(path, "config", "user.email", "fixture@example.invalid")
    _git(path, "commit", "--allow-empty", "-qm", "fixture")
    return path.resolve()


def test_repository_identity_is_independent_of_callers_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repository(tmp_path / "repo")
    foreign = _repository(tmp_path / "foreign")
    monkeypatch.chdir(repo)
    inside = _repository_identity(repo)
    monkeypatch.chdir(foreign)
    outside = _repository_identity(repo)

    assert outside == inside
    assert outside["identity"] == hashlib.sha256(str(repo / ".git").encode()).hexdigest()
    assert outside["identity"] != _repository_identity(foreign)["identity"]


def test_linked_worktree_and_primary_share_repository_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repository(tmp_path / "repo")
    linked = (tmp_path / "linked").resolve()
    _git(repo, "worktree", "add", "--detach", str(linked), "HEAD")
    monkeypatch.chdir(tmp_path)

    primary_identity = _repository_identity(repo)
    linked_identity = _repository_identity(linked)

    assert primary_identity["identity"] == linked_identity["identity"]
    assert primary_identity["head_sha"] == linked_identity["head_sha"]
    assert primary_identity["root"] != linked_identity["root"]
