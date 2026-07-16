from __future__ import annotations

from copy import deepcopy


def _evidence_slice() -> dict:
    from quality_runner.verification_contract import EVIDENCE_REQUIREMENTS

    return {
        "id": "remediate-structural-skill:test-strategy-review",
        "title": "Review test strategy finding",
        "priority": "medium",
        "findings": [
            {
                "id": "structural-skill:test-strategy-review",
                "severity": "observation",
                "category": "skill:test-strategy",
                "summary": "Review test evidence.",
                "file": "tests/example.test.ts",
                "line": 4,
                "fingerprint": "abc123",
            }
        ],
        "actions": ["Review the finding and record the decision."],
        "verification_gates": ["Review the test evidence in context."],
        "verification_mode": "evidence",
        "verification_requirements": list(EVIDENCE_REQUIREMENTS),
        "stop_conditions": ["Stop if the evidence no longer matches the file."],
        "planned_at": {"head": "abc", "branch": "main", "dirty": False},
        "scope": {"in_scope": ["tests/example.test.ts"], "out_of_scope": []},
    }


def test_review_evidence_is_machine_checkable_when_requirements_are_structured() -> None:
    from quality_runner.handoff_lint import validate_handoff_quality

    slice_item = _evidence_slice()
    handoff = {
        "implementation_allowed": False,
        "next_slice": deepcopy(slice_item),
    }
    result = validate_handoff_quality(handoff, remediation_plan={"slices": [slice_item]})

    assert result["passed"] is True, result["errors"]


def test_review_evidence_without_requirements_is_rejected() -> None:
    from quality_runner.handoff_lint import validate_handoff_quality

    slice_item = _evidence_slice()
    slice_item.pop("verification_requirements")
    handoff = {"implementation_allowed": False, "next_slice": deepcopy(slice_item)}
    result = validate_handoff_quality(handoff, remediation_plan={"slices": [slice_item]})

    assert result["passed"] is False
    assert any("invalid verification contract" in error for error in result["errors"])


def test_skill_finding_infers_evidence_mode_from_review_text() -> None:
    from quality_runner.planning_slices import slice_for_finding
    from quality_runner.verification_contract import EVIDENCE_REQUIREMENTS

    finding = {
        "id": "structural-skill:data-integrity-migration-review",
        "severity": "observation",
        "category": "skill:data-integrity",
        "summary": "Migration requires explicit review.",
        "recommended_fix": "Review the migration.",
        "verification": [
            "Review the migration against representative data and record the owner decision."
        ],
    }

    slice_item = slice_for_finding(finding)

    assert slice_item["verification_mode"] == "evidence"
    assert slice_item["verification_requirements"] == list(EVIDENCE_REQUIREMENTS)


def test_command_verification_remains_command_mode() -> None:
    from quality_runner.planning_slices import slice_for_finding

    finding = {
        "id": "missing-tests",
        "severity": "warning",
        "category": "capability",
        "summary": "Tests are missing.",
        "recommended_fix": "Add the test command.",
        "verification": ["pnpm test"],
    }

    slice_item = slice_for_finding(finding)

    assert slice_item["verification_mode"] == "command"
    assert "verification_requirements" not in slice_item
