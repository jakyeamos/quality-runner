from __future__ import annotations

from typing import Any


def _finding(
    finding_id: str,
    *,
    category: str = "capability",
    score: int = 10,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": "warning",
        "category": category,
        "summary": f"{finding_id} summary",
        "recommended_fix": f"Fix {finding_id}",
        "verification": ["Rerun quality-runner."],
        "score": score,
    }


def test_remediation_plan_starts_with_capability_gate_adoption_stage() -> None:
    from quality_runner.planning import build_remediation_plan, render_plan_markdown

    plan = build_remediation_plan(
        audit_report={
            "run_id": "capability-run",
            "profile": "default",
            "findings": [_finding("missing-tests")],
        },
        capability_map={
            "missing": [
                {
                    "id": "tests",
                    "reason": "No test script found.",
                    "language": "javascript",
                }
            ],
            "warnings": [],
        },
    )

    assert plan["adoption_stage"]["id"] == "phase-1-capability-gates"
    assert plan["stopping_criteria"] == [
        "Stop after missing repo-owned gates are added and verified.",
        "Do not chase broad structural findings in the same branch.",
    ]
    markdown = render_plan_markdown(plan)
    assert "## Adoption Stage" in markdown
    assert "- ID: phase-1-capability-gates" in markdown
    assert "## Stopping Criteria" in markdown


def test_agent_handoff_classifies_broad_structural_debt_before_one_shot_cleanup() -> None:
    from quality_runner.planning import (
        build_agent_handoff,
        build_remediation_plan,
        render_handoff_markdown,
    )

    audit_report = {
        "run_id": "broad-structural-run",
        "profile": "default",
        "findings": [
            _finding(
                f"structural-simplify-rule-{index}",
                category="structural:simplify",
                score=30,
            )
            for index in range(10)
        ],
    }
    capability_map = {"missing": [], "warnings": []}

    plan = build_remediation_plan(
        audit_report=audit_report,
        capability_map=capability_map,
    )
    handoff = build_agent_handoff(
        audit_report=audit_report,
        remediation_plan=plan,
        artifact_paths={"quality_audit_json": "/tmp/quality-audit.json"},
        capability_map=capability_map,
    )

    assert plan["adoption_stage"]["id"] == "phase-4-debt-classification"
    assert plan["adoption_stage"]["structural_finding_groups"] == 10
    assert plan["adoption_stage"]["structural_score"] == 300
    assert handoff["adoption_stage"] == plan["adoption_stage"]
    assert handoff["stopping_criteria"] == [
        "Stop after documenting broad structural debt and representative buckets.",
        "Convert remaining work into future refactor phases instead of attempting one-shot cleanup.",
    ]
    markdown = render_handoff_markdown(handoff)
    assert "- ID: phase-4-debt-classification" in markdown
    assert "Convert remaining work into future refactor phases" in markdown
