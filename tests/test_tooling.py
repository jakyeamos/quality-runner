from __future__ import annotations

from pathlib import Path

from quality_runner.tooling import (
    QUALITY_RUNNER_GIT_URL,
    command_text,
    current_runner_command,
    current_runner_source,
    current_source_root,
    latest_runner_command,
)


def test_current_runner_uses_the_checkout_that_produced_the_report(monkeypatch) -> None:
    monkeypatch.delenv("QUALITY_RUNNER_REPO", raising=False)
    source_root = Path(__file__).resolve().parents[1]

    assert current_source_root() == source_root
    assert current_runner_source() == str(source_root)
    assert current_runner_command(["--version"]) == [
        "uv",
        "run",
        "--project",
        str(source_root),
        "quality-runner",
        "--version",
    ]


def test_current_runner_accepts_an_explicit_checkout(monkeypatch, tmp_path: Path) -> None:
    source_root = tmp_path / "quality-runner"
    source_root.mkdir()
    (source_root / "pyproject.toml").write_text(
        '[project]\nname = "quality-runner"\n', encoding="utf-8"
    )
    monkeypatch.setenv("QUALITY_RUNNER_REPO", str(source_root))

    assert current_source_root() == source_root.resolve()
    assert command_text(current_runner_command(["refresh", "/tmp/repo"])) == (
        f"uv run --project {source_root} quality-runner refresh /tmp/repo"
    )


def test_latest_runner_resolves_the_refreshing_git_tool() -> None:
    assert latest_runner_command(["--version"]) == [
        "uvx",
        "--refresh",
        "--from",
        QUALITY_RUNNER_GIT_URL,
        "quality-runner",
        "--version",
    ]
