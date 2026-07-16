from __future__ import annotations

import subprocess
from pathlib import Path

from quality_runner.cli_update import update_command_payload


def test_self_update_uses_uv_tool_upgrade_when_no_editable_source(monkeypatch) -> None:
    monkeypatch.setattr("quality_runner.cli_update._editable_source", lambda: None)
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="updated\n", stderr="")

    monkeypatch.setattr("quality_runner.cli_update.subprocess.run", fake_run)

    payload = update_command_payload()

    assert payload["status"] == "updated"
    assert calls == [["uv", "tool", "upgrade", "quality-runner"]]


def test_self_update_reinstalls_explicit_checkout_in_editable_mode(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='quality-runner'\n")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="installed\n", stderr="")

    monkeypatch.setattr("quality_runner.cli_update.subprocess.run", fake_run)

    payload = update_command_payload(str(tmp_path))

    assert payload["status"] == "updated"
    assert calls == [["uv", "tool", "install", "--editable", str(tmp_path), "--force"]]


def test_self_update_blocks_invalid_source(tmp_path: Path) -> None:
    payload = update_command_payload(str(tmp_path))

    assert payload["status"] == "blocked"
    assert "not a Quality Runner checkout" in payload["error"]
