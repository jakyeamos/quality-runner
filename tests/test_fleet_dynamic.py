from __future__ import annotations

from pathlib import Path

from quality_runner.fleet import dynamic


def test_missing_dynamic_command_worktree_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    def missing_worktree(command: str, *, cwd: Path, timeout: int) -> dict[str, object]:
        del command, cwd, timeout
        raise FileNotFoundError("disposable worktree disappeared")

    monkeypatch.setattr(dynamic, "run_shell_command", missing_worktree)

    result = dynamic._run_dynamic_command(
        {"id": "tests", "command": "python -m pytest"},
        tmp_path / "missing-worktree",
        30,
    )

    assert result["status"] == "unavailable"
    assert result["command_id"] == "tests"
