from __future__ import annotations

from datetime import UTC, datetime

from quality_runner.task_findings import compare_findings, normalize_findings


def _occurrence(
    fingerprint: str,
    *,
    path: str = "src/app.py",
    enforced: bool = True,
    coverage_ref: str = "code_quality",
) -> dict[str, object]:
    return {
        "detector": "code_quality",
        "rule_id": "large-source-file",
        "fingerprint": fingerprint,
        "path": path,
        "line": 1,
        "severity": "warning",
        "confidence": "high",
        "coverage_ref": coverage_ref,
        "enforcement_eligible": enforced,
        "evidence": "501 lines",
    }


def _payload(rows: list[dict[str, object]], coverage: str = "complete") -> dict[str, object]:
    return {
        "coverage": {"code_quality": coverage},
        "occurrences": rows,
        "ambiguities": [],
    }


def test_normalization_only_enforces_behavior_verified_rule_with_all_fixtures() -> None:
    normalized = normalize_findings(
        code_quality_scan={
            "coverage": "complete",
            "findings": [
                {
                    "rule_id": "large-source-file",
                    "fingerprint": "abc",
                    "file": "src/app.py",
                    "line": 1,
                    "severity": "warning",
                    "confidence": "high",
                    "evidence": "501 lines",
                }
            ],
        },
        security_scan={"coverage": "complete", "candidates": []},
        prevention={
            "rules": [
                {
                    "detector": "code_quality",
                    "rule_id": "large-source-file",
                    "state": "behavior-verified",
                    "paths": ["src/**"],
                    "confidence_threshold": 1.0,
                    "evidence_refs": [
                        "positive:tests/fixtures/large.py",
                        "negative:tests/fixtures/small.py",
                        "ambiguous:tests/fixtures/generated.py",
                    ],
                }
            ]
        },
    )

    assert normalized["occurrences"][0]["enforcement_eligible"] is True


def test_normalization_derives_unique_occurrences_from_reused_detector_fingerprint() -> None:
    normalized = normalize_findings(
        code_quality_scan={
            "coverage": "complete",
            "findings": [
                {
                    "rule_id": "console-output",
                    "fingerprint": "shared-evidence-fingerprint",
                    "file": "src/app.ts",
                    "line": 10,
                    "severity": "warning",
                    "confidence": "high",
                },
                {
                    "rule_id": "console-output",
                    "fingerprint": "shared-evidence-fingerprint",
                    "file": "src/app.ts",
                    "line": 20,
                    "severity": "warning",
                    "confidence": "high",
                },
                {
                    "rule_id": "console-output",
                    "fingerprint": "shared-evidence-fingerprint",
                    "file": "src/other.ts",
                    "line": 10,
                    "severity": "warning",
                    "confidence": "high",
                },
            ],
        },
        security_scan={"coverage": "complete", "candidates": []},
        prevention={},
    )

    rows = normalized["occurrences"]
    assert {row["source_fingerprint"] for row in rows} == {"shared-evidence-fingerprint"}
    assert len({row["fingerprint"] for row in rows}) == 3
    assert normalized["ambiguities"] == []


def test_normalization_keeps_indistinguishable_same_location_duplicates_ambiguous() -> None:
    row = {
        "rule_id": "console-output",
        "fingerprint": "shared-evidence-fingerprint",
        "file": "src/app.ts",
        "line": 10,
        "severity": "warning",
        "confidence": "high",
    }
    normalized = normalize_findings(
        code_quality_scan={"coverage": "complete", "findings": [row, row]},
        security_scan={"coverage": "complete", "candidates": []},
        prevention={},
    )

    assert len(normalized["ambiguities"]) == 1
    assert "identifies 2 occurrences" in normalized["ambiguities"][0]["message"]


def test_delta_separates_new_persisted_resolved_advisory_and_out_of_scope() -> None:
    baseline = _payload([_occurrence("persist"), _occurrence("resolved", path="src/old.py")])
    current = _payload(
        [
            _occurrence("persist"),
            _occurrence("new"),
            _occurrence("advisory", enforced=False),
            _occurrence("outside", path="src/unchanged.py"),
        ]
    )

    result = compare_findings(
        baseline=baseline,
        current=current,
        changed_paths=["src/app.py", "src/old.py"],
        dispositions=[],
        required_modules=["code_quality"],
    )

    assert result["counts"] == {
        "new_enforced": 1,
        "persisted": 1,
        "resolved": 1,
        "waived": 0,
        "advisory": 1,
        "out_of_scope": 1,
        "unknown": 0,
    }
    assert result["blockers"] == []


def test_incomplete_follow_up_coverage_makes_absence_unknown_not_resolved() -> None:
    result = compare_findings(
        baseline=_payload([_occurrence("gone")]),
        current=_payload([], coverage="partial"),
        changed_paths=["src/app.py"],
        dispositions=[],
        required_modules=["code_quality"],
    )

    assert result["counts"]["resolved"] == 0
    assert result["counts"]["unknown"] == 1
    assert {item["code"] for item in result["blockers"]} == {
        "incomplete_comparable_coverage",
        "required_coverage_incomplete",
    }


def test_provisional_comparison_carries_incomplete_baseline_forward() -> None:
    result = compare_findings(
        baseline=_payload([_occurrence("deferred")]),
        current=_payload([], coverage="partial"),
        changed_paths=["src/app.py"],
        dispositions=[],
        required_modules=[],
        preserve_incomplete_baseline=True,
    )

    assert result["counts"]["persisted"] == 1
    assert result["counts"]["resolved"] == 0
    assert result["counts"]["unknown"] == 0
    assert result["blockers"] == []


def test_exact_fingerprint_waiver_requires_owner_reason_evidence_and_future_expiry() -> None:
    result = compare_findings(
        baseline=_payload([]),
        current=_payload([_occurrence("waived")]),
        changed_paths=["src/app.py"],
        dispositions=[
            {
                "fingerprint": "waived",
                "owner": "quality",
                "reason": "known generated boundary",
                "review_evidence": "issue:QR-1",
                "expires": "2030-01-01T00:00:00Z",
            }
        ],
        required_modules=["code_quality"],
        now=datetime(2029, 1, 1, tzinfo=UTC),
    )

    assert result["counts"]["waived"] == 1
    assert result["counts"]["new_enforced"] == 0


def test_duplicate_fingerprint_is_ambiguous_and_blocks() -> None:
    duplicated = _occurrence("same")
    current = _payload([duplicated, {**duplicated, "path": "src/other.py"}])
    current["ambiguities"] = [
        {
            "fingerprint": "code_quality:large-source-file:same",
            "message": "fingerprint identifies two occurrences",
        }
    ]

    result = compare_findings(
        baseline=_payload([]),
        current=current,
        changed_paths=["src/app.py", "src/other.py"],
        dispositions=[],
        required_modules=[],
    )

    assert result["counts"]["unknown"] == 1
    assert result["blockers"][0]["code"] == "ambiguous_occurrence_match"
