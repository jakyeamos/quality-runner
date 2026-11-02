from __future__ import annotations

from quality_runner.task_contract import (
    TASK_RELEASE_ENFORCEMENT_REQUIRED,
    enforce_release_eligibility,
    release_readiness,
)


def test_release_readiness_rejects_a_new_finding_even_when_other_findings_resolve() -> None:
    payload = release_readiness(
        mode="authoritative",
        delta={
            "counts": {
                "new_enforced": 1,
                "unknown": 0,
            },
            "blockers": [],
        },
        repository_blockers=[],
        contract_blockers=[],
        promotion_blockers=[],
        gate_blockers=[],
        readiness_blockers=[],
        required_gate_failures=[],
    )

    assert payload["predicate"] == "no_new_enforced_findings"
    assert payload["eligible"] is False
    assert payload["criteria"]["no_new_enforced_findings"] is False
    assert "no_new_enforced_findings" in payload["blocking_reasons"]


def test_required_release_enforcement_fail_closes_an_ineligible_pass() -> None:
    decision, blockers = enforce_release_eligibility(
        decision="pass",
        enforcement=TASK_RELEASE_ENFORCEMENT_REQUIRED,
        readiness={"eligible": False},
        blockers=[],
    )

    assert decision == "blocked"
    assert blockers == [
        {
            "code": "release_readiness_ineligible",
            "message": "release-check requires every release readiness criterion to pass",
        }
    ]
