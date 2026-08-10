from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from quality_runner.branch_diff import BRANCH_DIFF_SCOPE_BASIS, resolve_branch_diff
from quality_runner.cli import build_parser
from quality_runner.cli_refresh import refresh_command_payload


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo_root: Path, message: str) -> str:
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-m", message)
    return _git(repo_root, "rev-parse", "HEAD")


def _initialize(repo_root: Path) -> None:
    _git(repo_root, "init", "-b", "main")
    _git(repo_root, "config", "user.email", "quality-runner@example.test")
    _git(repo_root, "config", "user.name", "Quality Runner Tests")
    (repo_root / "src").mkdir()
    (repo_root / "src" / "shared.py").write_text("VALUE = 1\n", encoding="utf-8")
    _commit(repo_root, "base")


def test_branch_diff_resolves_merge_base_and_changed_paths(tmp_path: Path) -> None:
    _initialize(tmp_path)
    _git(tmp_path, "switch", "-c", "dev")
    (tmp_path / "src" / "dev.py").write_text("VALUE = 2\n", encoding="utf-8")
    dev_commit = _commit(tmp_path, "dev change")

    scope = resolve_branch_diff(tmp_path, base_ref="main", head_ref="dev")

    assert scope.base_commit == _git(tmp_path, "rev-parse", "main")
    assert scope.head_commit == dev_commit
    assert scope.comparison_base_commit == scope.base_commit
    assert scope.changed_paths == ("src/dev.py",)
    assert scope.working_tree_changed is False
    assert scope.to_payload() == {
        "scope_basis": BRANCH_DIFF_SCOPE_BASIS,
        "requested_base": "main",
        "requested_head": "dev",
        "base_commit": scope.base_commit,
        "head_commit": scope.head_commit,
        "comparison_base_commit": scope.comparison_base_commit,
        "checked_out_head_commit": scope.checked_out_head_commit,
        "head_matches_checked_out": True,
        "changed_paths": ["src/dev.py"],
        "scope_available": True,
        "working_tree_included": True,
        "working_tree_changed": False,
    }


def test_branch_diff_includes_working_tree_and_untracked_paths(tmp_path: Path) -> None:
    _initialize(tmp_path)
    _git(tmp_path, "switch", "-c", "dev")
    (tmp_path / "src" / "dev.py").write_text("VALUE = 2\n", encoding="utf-8")
    _commit(tmp_path, "dev change")
    (tmp_path / "src" / "dev.py").write_text("VALUE = 3\n", encoding="utf-8")
    (tmp_path / "src" / "local.py").write_text("VALUE = 4\n", encoding="utf-8")

    scope = resolve_branch_diff(tmp_path, base_ref="main", head_ref="dev")

    assert scope.changed_paths == ("src/dev.py", "src/local.py")
    assert scope.working_tree_changed is True


def test_branch_diff_fails_when_requested_head_is_not_checked_out(tmp_path: Path) -> None:
    _initialize(tmp_path)
    _git(tmp_path, "switch", "-c", "dev")
    (tmp_path / "src" / "dev.py").write_text("VALUE = 2\n", encoding="utf-8")
    _commit(tmp_path, "dev change")
    _git(tmp_path, "switch", "main")

    with pytest.raises(ValueError, match="does not match the checked-out HEAD"):
        resolve_branch_diff(tmp_path, base_ref="main", head_ref="dev")


def test_branch_diff_fails_closed_for_an_unresolvable_ref(tmp_path: Path) -> None:
    _initialize(tmp_path)

    with pytest.raises(ValueError, match="git branch diff command failed"):
        resolve_branch_diff(tmp_path, base_ref="missing-base")


def test_refresh_cli_forwards_branch_diff_scope_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _initialize(tmp_path)
    _git(tmp_path, "switch", "-c", "dev")
    (tmp_path / "src" / "dev.py").write_text("VALUE = 2\n", encoding="utf-8")
    _commit(tmp_path, "dev change")
    args = build_parser().parse_args(
        [
            "refresh",
            str(tmp_path),
            "--run-id-prefix",
            "branch-diff",
            "--diff-base",
            "main",
            "--diff-head",
            "dev",
        ]
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "quality_runner.cli_refresh.resolve_workflow_intent",
        lambda **_: {"goal": "find branch-diff findings"},
    )

    def fake_refresh(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"status": "stubbed"}

    monkeypatch.setattr("quality_runner.cli_refresh.refresh_payload", fake_refresh)

    assert refresh_command_payload(args, tmp_path) == {"status": "stubbed"}
    assert captured["focus_paths"] == ["src/dev.py"]
    scope_metadata = captured["scope_metadata"]
    assert isinstance(scope_metadata, dict)
    assert scope_metadata["requested_base"] == "main"
    assert scope_metadata["requested_head"] == "dev"
    assert scope_metadata["head_matches_checked_out"] is True
