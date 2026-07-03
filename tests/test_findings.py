from __future__ import annotations


def test_validate_audit_report_rejects_findings_without_evidence() -> None:
    from quality_runner.findings import validate_audit_report

    report = {
        "schema": "quality-runner-audit-report-v0.1",
        "findings": [
            {
                "id": "missing-evidence",
                "severity": "warning",
                "category": "docs",
                "summary": "No evidence",
                "evidence": [],
                "recommended_fix": "Add evidence",
                "verification": ["review report"],
            }
        ],
    }

    result = validate_audit_report(report)

    assert result["passed"] is False
    assert result["errors"] == ["finding missing-evidence has no evidence"]


def test_validate_audit_report_rejects_missing_schema() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report({"findings": []})

    assert result["passed"] is False
    assert result["errors"] == ["audit report schema must be quality-runner-audit-report-v0.1"]


def test_validate_audit_report_rejects_missing_required_finding_fields() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report(
        {
            "schema": "quality-runner-audit-report-v0.1",
            "findings": [{"evidence": ["line 1"]}],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == [
        "finding at index 0 field id must be a non-empty string",
        "finding at index 0 field severity must be a non-empty string",
        "finding at index 0 field category must be a non-empty string",
        "finding at index 0 field summary must be a non-empty string",
        "finding at index 0 field recommended_fix must be a non-empty string",
        "finding unknown has no verification",
    ]


def test_validate_audit_report_rejects_missing_findings() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report({})

    assert result["passed"] is False
    assert result["errors"] == [
        "audit report schema must be quality-runner-audit-report-v0.1",
        "audit report findings must be a list",
    ]


def test_validate_audit_report_rejects_non_list_findings() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report({"findings": "not-a-list"})

    assert result["passed"] is False
    assert result["errors"] == [
        "audit report schema must be quality-runner-audit-report-v0.1",
        "audit report findings must be a list",
    ]


def test_validate_audit_report_rejects_non_dict_findings() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report({"schema": "wrong", "findings": ["not-a-dict"]})

    assert result["passed"] is False
    assert result["errors"] == [
        "audit report schema must be quality-runner-audit-report-v0.1",
        "finding at index 0 is not an object",
    ]


def test_validate_audit_report_rejects_non_string_evidence_items() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report(
        {
            "schema": "quality-runner-audit-report-v0.1",
            "findings": [
                {
                    "id": "finding-001",
                    "severity": "warning",
                    "category": "docs",
                    "summary": "Bad evidence",
                    "evidence": [123],
                    "recommended_fix": "Use string evidence",
                    "verification": ["review report"],
                }
            ],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == ["finding finding-001 has no evidence"]


def test_validate_audit_report_rejects_empty_string_verification_items() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report(
        {
            "schema": "quality-runner-audit-report-v0.1",
            "findings": [
                {
                    "id": "finding-001",
                    "severity": "warning",
                    "category": "docs",
                    "summary": "Bad verification",
                    "evidence": ["line 1"],
                    "recommended_fix": "Use string verification",
                    "verification": [""],
                }
            ],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == ["finding finding-001 has no verification"]


def test_validate_remediation_plan_rejects_slices_without_verification_gates() -> None:
    from quality_runner.findings import validate_remediation_plan

    plan = {
        "schema": "quality-runner-remediation-plan-v0.1",
        "slices": [
            {
                "id": "slice-001",
                "title": "No verification",
                "priority": "high",
                "findings": [
                    {
                        "id": "finding-001",
                        "severity": "blocker",
                        "category": "capability",
                        "summary": "Missing tests",
                    }
                ],
                "actions": ["Add tests"],
                "verification_gates": [],
            }
        ],
    }

    result = validate_remediation_plan(plan)

    assert result["passed"] is False
    assert result["errors"] == ["slice slice-001 has no verification gates"]


def test_validate_remediation_plan_rejects_missing_schema() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan({"slices": []})

    assert result["passed"] is False
    assert result["errors"] == [
        "remediation plan schema must be quality-runner-remediation-plan-v0.1"
    ]


def test_validate_remediation_plan_rejects_missing_required_slice_fields() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan(
        {
            "schema": "quality-runner-remediation-plan-v0.1",
            "slices": [{"verification_gates": ["run tests"]}],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == [
        "slice at index 0 field id must be a non-empty string",
        "slice at index 0 field title must be a non-empty string",
        "slice at index 0 field priority must be a non-empty string",
        "slice unknown has no findings",
        "slice unknown has no actions",
    ]


def test_validate_remediation_plan_rejects_missing_slices() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan({})

    assert result["passed"] is False
    assert result["errors"] == [
        "remediation plan schema must be quality-runner-remediation-plan-v0.1",
        "remediation plan slices must be a list",
    ]


def test_validate_remediation_plan_rejects_non_list_slices() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan({"slices": "not-a-list"})

    assert result["passed"] is False
    assert result["errors"] == [
        "remediation plan schema must be quality-runner-remediation-plan-v0.1",
        "remediation plan slices must be a list",
    ]


def test_validate_remediation_plan_rejects_non_dict_slices() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan({"schema": "wrong", "slices": ["not-a-dict"]})

    assert result["passed"] is False
    assert result["errors"] == [
        "remediation plan schema must be quality-runner-remediation-plan-v0.1",
        "slice at index 0 is not an object",
    ]


def test_validate_remediation_plan_rejects_malformed_finding_items() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan(
        {
            "schema": "quality-runner-remediation-plan-v0.1",
            "slices": [
                {
                    "id": "slice-001",
                    "title": "Bad findings",
                    "priority": "high",
                    "findings": [None],
                    "actions": ["Add tests"],
                    "verification_gates": ["run tests"],
                }
            ],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == ["slice slice-001 has no findings"]


def test_validate_remediation_plan_rejects_non_string_verification_gate_items() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan(
        {
            "schema": "quality-runner-remediation-plan-v0.1",
            "slices": [
                {
                    "id": "slice-001",
                    "title": "Bad verification",
                    "priority": "high",
                    "findings": [
                        {
                            "id": "finding-001",
                            "severity": "blocker",
                            "category": "capability",
                            "summary": "Missing tests",
                        }
                    ],
                    "actions": ["Add tests"],
                    "verification_gates": [123],
                }
            ],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == ["slice slice-001 has no verification gates"]


def test_validate_remediation_plan_rejects_unknown_priority() -> None:
    from quality_runner.findings import validate_remediation_plan

    plan = {
        "schema": "quality-runner-remediation-plan-v0.1",
        "slices": [_valid_remediation_slice(priority="urgent")],
    }

    result = validate_remediation_plan(plan)

    assert result["passed"] is False
    assert result["errors"] == ["slice slice-001 priority is not in the allowed vocabulary"]


def test_validate_agent_handoff_rejects_unknown_status() -> None:
    from quality_runner.findings import validate_agent_handoff

    handoff = _valid_agent_handoff(status="started")

    result = validate_agent_handoff(handoff)

    assert result["passed"] is False
    assert result["errors"] == ["agent handoff status is not in the allowed vocabulary"]


def test_validate_agent_handoff_rejects_next_slice_unknown_priority() -> None:
    from quality_runner.findings import validate_agent_handoff

    handoff = _valid_agent_handoff()
    handoff["next_slice"] = _valid_remediation_slice(priority="urgent")

    result = validate_agent_handoff(handoff)

    assert result["passed"] is False
    assert result["errors"] == ["agent handoff next_slice must be a remediation slice object"]


def _valid_remediation_slice(priority: str = "high") -> dict[str, object]:
    return {
        "id": "slice-001",
        "title": "Fix missing tests",
        "priority": priority,
        "findings": [
            {
                "id": "finding-001",
                "severity": "blocker",
                "category": "capability",
                "summary": "Missing tests",
            }
        ],
        "actions": ["Add tests"],
        "verification_gates": ["Run tests"],
    }


def _valid_agent_handoff(status: str = "planned") -> dict[str, object]:
    return {
        "schema": "quality-runner-agent-handoff-v0.1",
        "status": status,
        "implementation_allowed": False,
        "artifact_paths": {"agent_handoff_json": "/tmp/agent-handoff.json"},
        "warnings": [],
        "finding_ids": ["finding-001"],
        "slice_ids": ["slice-001"],
        "next_slice": _valid_remediation_slice(),
        "verification_gates": ["Run tests"],
    }
