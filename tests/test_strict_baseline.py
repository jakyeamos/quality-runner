from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from quality_runner.strict_baseline import build_baseline, compare_baseline, normalize_diagnostics


def _payload(*, line: int = 4, message: str = "Type of item is unknown") -> dict[str, object]:
    return {
        "version": "1.39.0",
        "summary": {
            "filesAnalyzed": 1,
            "errorCount": 1,
            "warningCount": 0,
            "informationCount": 0,
        },
        "generalDiagnostics": [
            {
                "file": "/repo/src/app.py",
                "severity": "error",
                "message": message,
                "rule": "reportUnknownVariableType",
                "range": {
                    "start": {"line": line, "character": 2},
                    "end": {"line": line, "character": 6},
                },
            }
        ],
    }


def _baseline(payload: dict[str, object]) -> dict[str, object]:
    return build_baseline(
        payload,
        root=Path("/repo"),
        baseline_ref="abc123",
        config_path="pyrightconfig.strict.json",
        config_sha256="config-hash",
    )


def test_fingerprint_survives_line_movement() -> None:
    before = normalize_diagnostics(_payload(line=4), Path("/repo"))
    after = normalize_diagnostics(_payload(line=40), Path("/repo"))

    assert before[0]["fingerprint"] == after[0]["fingerprint"]
    assert before[0]["start"] != after[0]["start"]


def test_legacy_occurrences_are_blocked_not_passed() -> None:
    baseline = _baseline(_payload())
    delta = compare_baseline(baseline, _baseline(_payload()), expected_config_sha256="config-hash")

    assert delta["state"] == "blocked"
    assert delta["legacy_count"] == 1
    assert delta["new"] == []


def test_delta_classifies_new_persisted_and_resolved() -> None:
    baseline = _baseline(_payload())
    current_payload = _payload(message="Type of value is unknown")
    current_payload["generalDiagnostics"] = [
        *current_payload["generalDiagnostics"],
        {
            "file": "/repo/src/new.py",
            "severity": "error",
            "message": "Argument type is unknown",
            "rule": "reportUnknownArgumentType",
            "range": {
                "start": {"line": 2, "character": 0},
                "end": {"line": 2, "character": 3},
            },
        },
    ]
    current_payload["summary"] = {
        "filesAnalyzed": 2,
        "errorCount": 2,
        "warningCount": 0,
        "informationCount": 0,
    }
    current = _baseline(current_payload)

    delta = compare_baseline(baseline, current, expected_config_sha256="config-hash")

    assert delta["state"] == "failing"
    assert len(delta["new"]) == 2
    assert len(delta["persisted"]) == 0
    assert len(delta["resolved"]) == 1
    assert delta["blockers"] == []


def test_repeated_group_count_change_is_unknown() -> None:
    payload = _payload()
    payload["generalDiagnostics"] = [
        *payload["generalDiagnostics"],
        {
            **payload["generalDiagnostics"][0],
            "range": {
                "start": {"line": 8, "character": 2},
                "end": {"line": 8, "character": 6},
            },
        },
    ]
    payload["summary"] = {
        "filesAnalyzed": 1,
        "errorCount": 2,
        "warningCount": 0,
        "informationCount": 0,
    }
    baseline = _baseline(_payload())
    current = _baseline(payload)

    delta = compare_baseline(baseline, current, expected_config_sha256="config-hash")

    assert delta["unknown"]
    assert any("occurrence matching is ambiguous" in blocker for blocker in delta["blockers"])


def test_repeated_group_that_disappears_is_resolved() -> None:
    payload = _payload()
    payload["generalDiagnostics"] = [
        *payload["generalDiagnostics"],
        {
            **payload["generalDiagnostics"][0],
            "range": {
                "start": {"line": 8, "character": 2},
                "end": {"line": 8, "character": 6},
            },
        },
    ]
    payload["summary"] = {
        "filesAnalyzed": 1,
        "errorCount": 2,
        "warningCount": 0,
        "informationCount": 0,
    }
    baseline = _baseline(payload)
    current = _baseline(
        {
            **_payload(),
            "summary": {
                "filesAnalyzed": 1,
                "errorCount": 0,
                "warningCount": 0,
                "informationCount": 0,
            },
            "generalDiagnostics": [],
        }
    )

    delta = compare_baseline(baseline, current, expected_config_sha256="config-hash")

    assert len(delta["resolved"]) == 2
    assert delta["unknown"] == []
    assert delta["state"] == "passed"


def test_strict_baseline_intentional_failure_fixture(tmp_path: Path) -> None:
    source = tmp_path / "src" / "fixture.py"
    source.parent.mkdir()
    source.write_text("value: str = 1\n", encoding="utf-8")
    config = tmp_path / "pyrightconfig.strict.json"
    config.write_text(
        '{"include": ["src"], "pythonVersion": "3.12", "typeCheckingMode": "strict"}\n',
        encoding="utf-8",
    )
    script = Path(__file__).parents[1] / "scripts" / "check_strict_baseline.py"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(script.parents[1]), environment.get("PYTHONPATH", "")]
    )
    command = [
        sys.executable,
        str(script),
        "--root",
        str(tmp_path),
        "--baseline",
        "baseline.json",
        "--config",
        "pyrightconfig.strict.json",
        "--update",
        "--reason",
        "intentional failure fixture baseline",
    ]
    check_command = command[:8]

    created = subprocess.run(command, capture_output=True, text=True, env=environment, check=False)
    assert created.returncode == 0, created.stderr

    unchanged = subprocess.run(
        check_command, capture_output=True, text=True, env=environment, check=False
    )
    assert unchanged.returncode == 0, unchanged.stderr
    assert "state=blocked" in unchanged.stdout

    source.write_text("value: str = 1\nother: int = 'new'\n", encoding="utf-8")
    failed = subprocess.run(
        check_command, capture_output=True, text=True, env=environment, check=False
    )
    assert failed.returncode == 1
    assert "state=failing" in failed.stdout
    assert "new=1" in failed.stdout
