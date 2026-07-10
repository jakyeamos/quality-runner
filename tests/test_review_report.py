from __future__ import annotations

import json
from pathlib import Path

import pytest


def _finding(**overrides: object) -> dict[str, object]:
    finding: dict[str, object] = {
        "id": "FR-001",
        "fingerprint": "sha256:one",
        "severity": "high",
        "classification": "suspected",
        "confidence": "medium",
        "summary": "A route appears unreachable.",
        "why_it_matters": "Users may not reach the completed feature.",
        "location": ["src/routes.py"],
        "evidence": ["src/routes.py:12"],
        "recommended_fix": "Trace the route and navigation path.",
        "agent_prompt": "Investigate the route and fix only confirmed wiring issues.",
        "human_confirmation_required": True,
        "status": "needs-confirmation",
    }
    finding.update(overrides)
    return finding


def test_review_report_counts_findings_and_preserves_sections() -> None:
    from quality_runner.review_report import build_review_report

    report = build_review_report(
        run_id="review-001",
        mode="task",
        scope="task",
        breadth="focused",
        findings=[_finding()],
        evidence_used=["src/routes.py"],
        evidence_unavailable=["runtime observation"],
        exclusions=["styling"],
        adapter_status="review-complete",
        task_provenance="task-file.md",
    )

    assert report["severity_counts"] == {"critical": 0, "high": 1, "medium": 0, "low": 0}
    assert report["summary"] == "Review complete: 0 critical, 1 high, 0 medium issues found."
    assert report["sections"]["missed_requirements"] == []
    assert report["sections"]["suspected_issues"][0]["id"] == "FR-001"
    assert report["evidence_unavailable"] == ["runtime observation"]
    assert report["exclusions"] == ["styling"]


def test_no_issue_report_includes_end_to_end_caveat() -> None:
    from quality_runner.review_report import build_review_report

    report = build_review_report(
        run_id="review-002",
        mode="blind",
        scope="project",
        breadth="related",
        findings=[],
        evidence_used=[],
        evidence_unavailable=["browser access"],
        exclusions=[],
        adapter_status="review-complete",
        task_provenance=None,
    )

    assert "No major issues found from available evidence" in report["summary"]
    assert "does not prove the feature works end-to-end" in report["summary"]
    assert report["sections"]["missed_requirements"] == []


def test_report_rejects_invalid_confidence_and_missing_finding_fields() -> None:
    from quality_runner.review_report import build_review_report

    with pytest.raises(ValueError, match="confidence"):
        build_review_report(
            run_id="review-003",
            mode="task",
            scope="task",
            breadth="focused",
            findings=[_finding(confidence="certain")],
            evidence_used=[],
            evidence_unavailable=[],
            exclusions=[],
            adapter_status="review-complete",
            task_provenance="task.md",
        )

    missing = _finding()
    del missing["agent_prompt"]
    with pytest.raises(ValueError, match="agent_prompt"):
        build_review_report(
            run_id="review-004",
            mode="task",
            scope="task",
            breadth="focused",
            findings=[missing],
            evidence_used=[],
            evidence_unavailable=[],
            exclusions=[],
            adapter_status="review-complete",
            task_provenance="task.md",
        )


def test_review_report_schema_has_required_sections_and_fields() -> None:
    path = Path(__file__).parents[1] / "quality_runner" / "schemas" / "review-report.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))

    assert schema["properties"]["schema"]["const"] == "quality-runner-review-report-v0.1"
    assert set(schema["required"]) >= {"summary", "severity_counts", "sections", "findings"}
    assert schema["properties"]["sections"]["required"] == [
        "missed_requirements",
        "confirmed_issues",
        "suspected_issues",
        "not_enough_evidence",
        "project_consistency_risks",
        "regression_risks",
        "known_accepted_issues",
        "suggested_fixes",
        "agent_handoff_prompts",
        "remaining_uncertainty",
    ]
