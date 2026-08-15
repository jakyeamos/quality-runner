from __future__ import annotations

from quality_runner.fleet.contracts import DIMENSION_LABELS, DIMENSIONS
from quality_runner.fleet.error_codes import assess_stable_error_codes
from quality_runner.fleet.legibility import audit_repository
from quality_runner.fleet.maturity_feed import _repository_projection


def _write_full_contract(root) -> None:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "docs").mkdir()
    (root / "src" / "errors.ts").write_text(
        """
export const ErrorCodes = {
  INVALID_REQUEST: "demo.invalid_request",
  NOT_FOUND: "demo.not_found",
} as const;
export type ErrorCode = typeof ErrorCodes[keyof typeof ErrorCodes];
export function toResponse(errorCode: ErrorCode) {
  return { errorCode, response: { ok: false } };
}
""",
        encoding="utf-8",
    )
    (root / "tests" / "errors.test.ts").write_text(
        'expect(toResponse(ErrorCodes.INVALID_REQUEST).errorCode).toBe("demo.invalid_request");\n',
        encoding="utf-8",
    )
    (root / "docs" / "errors.md").write_text(
        "Stable machine-readable error codes are part of the public error contract.\n",
        encoding="utf-8",
    )


def test_stable_error_codes_reaches_maintained_with_four_evidence_signals(tmp_path) -> None:
    _write_full_contract(tmp_path)

    assessment = assess_stable_error_codes(tmp_path)

    assert assessment["score"] == 4
    assert assessment["status"] == "maintained"
    assert any(item["detail"] == "error-code documentation" for item in assessment["evidence"])
    assert any(
        item["detail"] == "machine-readable error propagation" for item in assessment["evidence"]
    )


def test_stable_error_codes_is_not_applicable_without_runtime_source(tmp_path) -> None:
    (tmp_path / "README.md").write_text("Documentation-only repository.\n", encoding="utf-8")

    assessment = assess_stable_error_codes(tmp_path)

    assert assessment["score"] is None
    assert assessment["status"] == "not_applicable"


def test_stable_error_codes_is_absent_when_source_has_no_machine_readable_contract(
    tmp_path,
) -> None:
    (tmp_path / "main.py").write_text('raise ValueError("request failed")\n', encoding="utf-8")

    assessment = assess_stable_error_codes(tmp_path)

    assert assessment["score"] == 0
    assert assessment["status"] == "absent"


def test_stable_error_codes_is_a_first_class_audit_dimension(tmp_path) -> None:
    _write_full_contract(tmp_path)

    report = audit_repository(
        repository={"repo_id": "fixture", "primary_path": str(tmp_path)},
        as_of="2026-08-13T12:00:00+00:00",
        run_id="fixture-run",
    )

    finding = next(
        item
        for item in report["findings"]
        if item["dimension"] == "diagnosability.stable_error_codes"
    )
    assert finding["score"] == 4
    assert finding["label"] == "stable error codes"
    assert "diagnosability.stable_error_codes" in DIMENSIONS
    assert DIMENSION_LABELS["diagnosability.stable_error_codes"] == "stable error codes"


def test_maturity_feed_preserves_stable_error_code_dimension_and_gap() -> None:
    projection = _repository_projection(
        {
            "repo_id": "fixture",
            "primary_path": "/projects/fixture",
            "target_branch": {"branch": "main", "status": "ready", "head": "abc"},
        },
        {
            "repo_id": "fixture",
            "findings": [
                {
                    "dimension": "diagnosability.stable_error_codes",
                    "status": "absent",
                    "score": 0,
                    "severity": "observation",
                    "priority": "P1",
                    "message": "No stable error-code contract was found.",
                }
            ],
            "dynamic": {"status": "not_selected"},
            "agent_usability": {},
        },
    )

    assert projection["dimension_scores"]["diagnosability.stable_error_codes"] == 0
    assert projection["dimension_gaps"][0]["dimension"] == "diagnosability.stable_error_codes"
