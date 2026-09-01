from __future__ import annotations

import json
from pathlib import Path

from quality_runner.verification_signals import analyze_verification_signals


def test_inspect_repo_reports_declarations_without_claiming_execution(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "test": "vitest run",
                    "test:coverage": "vitest run --coverage",
                    "mutation": "stryker run",
                }
            }
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="verification-signals-001")

    coverage = scan["verification_signals"]["coverage"]
    assert coverage["status"] == "declared"
    assert coverage["execution"] == "not_observed"
    assert coverage["observations"] == [
        {
            "source": "package.json:scripts.test:coverage",
            "source_type": "package_script",
            "evidence": "coverage flag",
        }
    ]
    mutation = scan["verification_signals"]["mutation"]
    assert mutation["status"] == "declared"
    assert mutation["execution"] == "not_observed"
    assert mutation["observations"] == [
        {
            "source": "package.json:scripts.mutation",
            "source_type": "package_script",
            "evidence": "mutation runner",
        }
    ]


def test_plain_test_command_does_not_imply_coverage_or_mutation() -> None:
    signals = analyze_verification_signals(
        scripts={"test": "vitest run"},
        quality_commands=[
            {
                "id": "tests",
                "command": "vitest run",
                "source_type": "package_script",
                "source": "package.json:scripts.test",
            }
        ],
    )

    assert signals["coverage"] == {
        "status": "not_declared",
        "execution": "not_observed",
        "observations": [],
    }
    assert signals["mutation"] == {
        "status": "not_declared",
        "execution": "not_observed",
        "observations": [],
    }


def test_empty_scan_is_unknown_and_duplicate_sources_are_collapsed() -> None:
    assert analyze_verification_signals(scripts={}, quality_commands=[]) == {
        "coverage": {
            "status": "unknown",
            "execution": "not_observed",
            "observations": [],
        },
        "mutation": {
            "status": "unknown",
            "execution": "not_observed",
            "observations": [],
        },
    }

    signals = analyze_verification_signals(
        scripts={"coverage": "pytest --cov"},
        quality_commands=[
            {
                "id": "tests",
                "command": "pytest --cov",
                "source_type": "package_script",
                "source": "package.json:scripts.coverage",
            }
        ],
    )
    assert len(signals["coverage"]["observations"]) == 1
