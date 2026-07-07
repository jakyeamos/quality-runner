from __future__ import annotations


def _integrate_finding() -> dict[str, object]:
    return {
        "id": "CQ-0001",
        "fingerprint": "abc123",
        "category": "integrate",
        "severity": "warning",
        "confidence": "medium",
        "score": 6,
        "file": "src/draft_feature.py",
        "line": 3,
        "rule_id": "stub-implementation",
        "evidence": "raise NotImplementedError",
        "expected_improvement": "Decide whether to wire or finish this work.",
        "risk": "Incomplete work is not reachable.",
        "verification": "python3.14 -m pytest -q",
        "remediation_bucket": "Integration and wiring decisions",
    }


def test_wiring_decision_slices_offer_explicit_dispositions() -> None:
    from quality_runner.remediation_wiring import wiring_decision_slices

    slices = wiring_decision_slices({"findings": [_integrate_finding()]})

    assert len(slices) == 1
    slice_item = slices[0]
    assert slice_item["id"] == "decide-wiring-src-draft-feature-py"
    assert slice_item["disposition_required"] is True
    assert {group["class"] for group in slice_item["action_groups"]} == {
        "wire",
        "finish",
        "descope",
        "accept-wip",
    }
    assert slice_item["findings"][0]["actionability"] == "needs-author-decision"


def test_remediation_plan_uses_wiring_slice_instead_of_structural_cluster() -> None:
    from quality_runner.planning import build_agent_handoff, build_remediation_plan

    audit_report = {
        "run_id": "run-001",
        "profile": "default",
        "findings": [
            {
                "id": "structural-integrate-stub-implementation",
                "severity": "warning",
                "category": "structural:integrate",
                "summary": "partial work",
                "recommended_fix": "choose disposition",
                "verification": ["python3.14 -m pytest -q"],
                "actionability": "needs-author-decision",
                "actionability_rationale": "needs a decision",
                "score": 6,
            }
        ],
    }
    plan = build_remediation_plan(
        audit_report=audit_report,
        capability_map={"missing": [], "warnings": []},
        code_quality_scan={"findings": [_integrate_finding()]},
    )
    handoff = build_agent_handoff(
        audit_report=audit_report,
        remediation_plan=plan,
        artifact_paths={"quality_audit_json": "/tmp/quality-audit.json"},
        capability_map={"missing": [], "warnings": []},
    )

    assert [slice_item["id"] for slice_item in plan["slices"]] == [
        "decide-wiring-src-draft-feature-py"
    ]
    assert handoff["next_slice"]["id"] == "decide-wiring-src-draft-feature-py"
    assert handoff["next_slice"]["action_groups"][0]["finding_ids"] == ["CQ-0001"]
