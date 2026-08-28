from __future__ import annotations

import subprocess
from pathlib import Path

from quality_runner.dogfood import codex_hook_payload, dogfood_report

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _enrolled_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "clone", "--quiet", "--no-checkout", str(ROOT), ".")
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    (repo / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.structural_scan]",
                "large_file_lines = 5",
                "similarity_enabled = false",
                "",
                "[quality_runner.prevention]",
                'required_modules = ["code_quality"]',
                "",
                "[[quality_runner.prevention.rules]]",
                'detector = "code_quality"',
                'rule_id = "large-source-file"',
                'state = "behavior-verified"',
                'owner = "quality"',
                'rationale = "Large source files increase review cost."',
                'evidence_refs = ["positive:test", "negative:test", "ambiguous:test"]',
                'paths = ["**/*.py", "*.py"]',
                "confidence_threshold = 0.3",
            ]
        ),
        encoding="utf-8",
    )
    return repo


def test_hook_ignores_unenrolled_repository(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()

    result = codex_hook_payload(
        {"cwd": str(tmp_path), "session_id": "session", "hook_event_name": "SessionStart"},
        state_dir=tmp_path / "state",
    )

    assert result == {}


def test_hook_rejects_invalid_lifecycle_payload(tmp_path: Path) -> None:
    result = codex_hook_payload({"cwd": str(tmp_path)}, state_dir=tmp_path / "state")

    assert result == {"systemMessage": "Quality Runner hook received an invalid lifecycle payload."}


def test_hook_starts_allows_unchanged_and_blocks_a_new_finding(tmp_path: Path) -> None:
    repo = _enrolled_repo(tmp_path)
    state = tmp_path / "dogfood-state"
    common = {"cwd": str(repo), "session_id": "fresh-session"}

    started = codex_hook_payload(
        {**common, "hook_event_name": "SessionStart"},
        state_dir=state,
    )
    unchanged = codex_hook_payload(
        {**common, "hook_event_name": "Stop"},
        state_dir=state,
    )
    (repo / "app.py").write_text(
        "\n".join(f"value_{index} = {index}" for index in range(8)) + "\n",
        encoding="utf-8",
    )
    blocked = codex_hook_payload(
        {**common, "hook_event_name": "Stop"},
        state_dir=state,
    )

    assert started["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert unchanged == {}
    assert blocked["decision"] == "block"
    report = dogfood_report(state)
    assert report["coverage"]["event_counts"] == {
        "quality_runner.task.release.check": 1,
        "quality_runner.task.start": 1,
        "quality_runner.task.stop.unchanged": 1,
    }
    assert report["feedback_loop"]["new_enforced_findings"] == 1
