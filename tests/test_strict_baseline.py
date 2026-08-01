from __future__ import annotations

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
