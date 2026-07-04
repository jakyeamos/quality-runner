from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quality_evidence_contract import (  # noqa: E402
    QUALITY_FINDING_SCHEMA,
    normalize_quality_finding,
    quality_finding_counts,
    validate_quality_finding,
)


def test_normalize_quality_finding_preserves_legacy_text_evidence() -> None:
    finding = normalize_quality_finding(
        criterion_id="testing-trust",
        criterion_title="Testing Trust",
        criterion_scope="global",
        level="blocker",
        summary="Missing behavior proof.",
        evidence=["tests/test_example.py"],
        metadata={"risk": "regression"},
        source="unit-test",
    )

    assert finding["schema"] == QUALITY_FINDING_SCHEMA
    assert finding["blocking"] is True
    assert finding["evidence_text"] == ["tests/test_example.py"]
    assert finding["evidence"][0]["summary"] == "tests/test_example.py"
    assert validate_quality_finding(finding)["passed"] is True


def test_quality_finding_counts_treats_error_as_blocker() -> None:
    findings = [
        normalize_quality_finding(
            criterion_id="a",
            level="pass",
            summary="ok",
        ),
        normalize_quality_finding(
            criterion_id="b",
            level="warning",
            summary="warn",
        ),
        normalize_quality_finding(
            criterion_id="c",
            level="critical",
            summary="critical",
        ),
    ]

    assert quality_finding_counts(findings) == {"pass": 1, "warning": 1, "blocker": 1}


def test_quality_runner_exports_quality_evidence_contract() -> None:
    from quality_runner import normalize_quality_finding as runner_normalize_quality_finding

    finding = runner_normalize_quality_finding(
        criterion_id="runtime-proof",
        level="error",
        summary="Runtime smoke is missing.",
        evidence=[{"command": "quality-runner verify-gates .", "status": "blocked"}],
    )

    assert finding["schema"] == QUALITY_FINDING_SCHEMA
    assert finding["blocking"] is True
    assert finding["evidence"][0]["command"] == "quality-runner verify-gates ."
