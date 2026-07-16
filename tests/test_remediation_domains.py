from __future__ import annotations

from pathlib import Path


def _finding(
    finding_id: str,
    *,
    category: str,
    severity: str = "warning",
) -> dict[str, str]:
    return {
        "id": finding_id,
        "severity": severity,
        "category": category,
        "summary": f"{finding_id} summary",
    }


def _slice(
    slice_id: str,
    *,
    category: str,
    priority: str = "medium",
    disposition_required: bool = False,
) -> dict[str, object]:
    return {
        "id": slice_id,
        "title": f"Remediate {slice_id}",
        "priority": priority,
        "disposition_required": disposition_required,
        "findings": [_finding(f"finding-{slice_id}", category=category)],
        "actions": [f"Fix {slice_id}"],
        "verification_gates": [f"Verify {slice_id}"],
    }


def test_domain_candidates_group_leaf_slices_without_discarding_forensic_ids() -> None:
    from quality_runner.remediation_domains import (
        annotate_remediation_slices,
        build_phase_candidates,
    )

    leaves = annotate_remediation_slices(
        [
            _slice("security-one", category="security:dangerous-sink", priority="high"),
            _slice("security-two", category="security:secrets-exposure", priority="medium"),
            _slice("ui-one", category="structural:ui_structural"),
            _slice(
                "integration-one",
                category="structural:integrate",
                disposition_required=True,
            ),
        ]
    )

    candidates = build_phase_candidates(leaves)

    assert [candidate["id"] for candidate in candidates] == [
        "phase-security",
        "phase-ui-quality",
        "phase-integration-decisions",
    ]
    security = candidates[0]
    assert security["slice_count"] == 2
    assert security["slice_ids"] == ["security-one", "security-two"]
    assert security["finding_ids"] == ["finding-security-one", "finding-security-two"]
    assert security["representative_slice_ids"] == ["security-one", "security-two"]
    integration = candidates[-1]
    assert integration["requires_review"] is True
    assert integration["status"] == "review-required"


def test_build_plan_defaults_to_domain_view_and_keeps_leaf_view() -> None:
    from quality_runner.findings import validate_remediation_plan
    from quality_runner.planning import build_remediation_plan, render_plan_markdown

    plan = build_remediation_plan(
        audit_report={
            "run_id": "domain-plan-run",
            "profile": "default",
            "findings": [
                {
                    "id": "security-finding",
                    "severity": "blocker",
                    "category": "security:dangerous-sink",
                    "summary": "Unsafe sink",
                    "recommended_fix": "Replace the sink.",
                    "verification": ["Run security tests."],
                    "score": 40,
                },
                {
                    "id": "missing-tests",
                    "severity": "blocker",
                    "category": "capability",
                    "summary": "Tests are missing",
                    "recommended_fix": "Add a test command.",
                    "verification": ["Run the test command."],
                    "score": 20,
                },
            ],
        },
        capability_map={"missing": [], "warnings": []},
    )

    assert plan["planning_mode"] == "domain"
    assert plan["leaf_slice_count"] == len(plan["slices"])
    assert plan["phase_candidate_count"] == 2
    assert {candidate["domain"] for candidate in plan["phase_candidates"]} == {
        "security",
        "quality-gates",
    }
    assert {item["id"] for item in plan["slices"]} == {
        "remediate-security-finding",
        "remediate-missing-tests",
    }
    assert validate_remediation_plan(plan) == {"passed": True, "errors": []}
    markdown = render_plan_markdown(plan)
    assert "## Domain Phase Candidates" in markdown
    assert "## Slices (forensic detail)" in markdown
    assert "### phase-security" in markdown


def test_phase_source_uses_domain_candidates_when_present(tmp_path: Path) -> None:
    from quality_runner.phase_sources import load_planning_source

    run_dir = tmp_path / ".quality-runner" / "runs" / "domain-run"
    run_dir.mkdir(parents=True)
    plan_path = run_dir / "remediation-plan.json"
    plan_path.write_text(
        '{"phase_candidates": [{"id": "phase-security", "domain": "security"}], '
        '"slices": [{"id": "leaf-security"}]}\n',
        encoding="utf-8",
    )
    source = load_planning_source(tmp_path, run_id="domain-run", handoff_json=None)

    assert source["planning_mode"] == "domain"
    assert source["slices"] == [{"id": "phase-security", "domain": "security"}]


def test_phase_source_can_select_one_domain_candidate(tmp_path: Path) -> None:
    from quality_runner.phase_sources import load_planning_source

    run_dir = tmp_path / ".quality-runner" / "runs" / "domain-run"
    run_dir.mkdir(parents=True)
    (run_dir / "remediation-plan.json").write_text(
        '{"phase_candidates": [{"id": "phase-security"}, {"id": "phase-ui-quality"}], '
        '"slices": []}\n',
        encoding="utf-8",
    )

    source = load_planning_source(
        tmp_path,
        run_id="domain-run",
        handoff_json=None,
        candidate_id="phase-security",
    )

    assert source["planning_mode"] == "domain"
    assert source["slices"] == [{"id": "phase-security"}]
    assert source["source"]["candidate_id"] == "phase-security"


def test_native_phase_plan_reads_domain_finding_ids_and_fingerprints() -> None:
    from quality_runner.phase_builder import build_phase_plan

    plan = build_phase_plan(
        phase={"number": 1},
        plan_number=1,
        slice_item={
            "id": "phase-security",
            "domain": "security",
            "workstreams": ["unsafe-sinks"],
            "title": "Security and trust boundaries",
            "priority": "high",
            "slice_ids": ["leaf-security"],
            "finding_ids": ["finding-security"],
            "finding_fingerprints": ["fingerprint-security"],
            "actions": ["Review the security leaf."],
            "verification_gates": ["Run security tests."],
        },
        source={"source": {"run_id": "domain-run"}},
        plan_ids_by_slice={"phase-security": 1},
        wave_by_slice={"phase-security": 1},
    )

    assert plan["finding_ids"] == ["finding-security"]
    assert plan["finding_fingerprints"] == ["fingerprint-security"]
    assert plan["source_slice_ids"] == ["leaf-security"]
    assert plan["domain"] == "security"
