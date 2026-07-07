from __future__ import annotations


def test_dead_code_output_becomes_unwired_decision_candidate() -> None:
    from quality_runner.unwired_from_dead_code import dead_code_unwired_findings

    findings = dead_code_unwired_findings(
        gate_verification={
            "gates": [
                {
                    "id": "dead_code",
                    "status": "failed",
                    "stdout": "src/draft_checkout.py:10: unused function 'draft_checkout' (60% confidence)",
                    "stderr": "",
                }
            ]
        },
        existing_findings=[],
        config={},
    )

    assert len(findings) == 1
    finding = findings[0]
    assert finding["category"] == "integrate"
    assert finding["rule_id"] == "dead-code-unwired-candidate"
    assert "wire" in finding["expected_improvement"]
    assert "remove" not in finding["expected_improvement"].lower()
    assert "prune" not in finding["expected_improvement"].lower()


def test_dead_code_output_ignores_plain_unused_symbols() -> None:
    from quality_runner.unwired_from_dead_code import dead_code_unwired_findings

    findings = dead_code_unwired_findings(
        gate_verification={
            "gates": [
                {
                    "id": "dead_code",
                    "status": "failed",
                    "stdout": "src/math.py:10: unused function 'add_numbers' (60% confidence)",
                }
            ]
        },
        existing_findings=[],
        config={},
    )

    assert findings == []


def test_merge_dead_code_unwired_findings_updates_scan_summary() -> None:
    from quality_runner.unwired_from_dead_code import merge_dead_code_unwired_findings

    scan = {
        "schema": "quality-runner-code-quality-scan-v0.1",
        "summary": {
            "total_findings": 0,
            "findings_by_category": {},
            "findings_by_severity": {},
        },
        "accountability": [],
        "findings": [],
        "duplicate_clusters": [],
        "skipped_files": [],
    }
    merged = merge_dead_code_unwired_findings(
        scan,
        {
            "gates": [
                {
                    "id": "dead_code",
                    "status": "failed",
                    "stdout": "src/wip_report.py:4: unused class 'WipReport' (60% confidence)",
                }
            ]
        },
        {},
    )

    assert merged["summary"]["total_findings"] == 1
    assert merged["summary"]["findings_by_category"]["integrate"] == 1
    assert merged["findings"][0]["id"] == "CQ-0001"
