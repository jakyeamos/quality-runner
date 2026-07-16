from __future__ import annotations

from quality_runner.resolution import (
    apply_audit_resolutions,
    filter_resolved_code_quality_scan,
)


def test_partial_resolution_stays_actionable_and_filters_only_resolved_rows() -> None:
    report = {
        "status": "findings",
        "findings": [{"id": "structural-harden-explicit-any"}],
    }
    code_quality_scan = {
        "findings": [
            {
                "fingerprint": "accepted-row",
                "category": "harden",
                "rule_id": "explicit-any",
            },
            {
                "fingerprint": "unresolved-row",
                "category": "harden",
                "rule_id": "explicit-any",
            },
        ],
        "summary": {"total_findings": 2},
    }
    ledger = {
        "entries": [
            {"fingerprint": "accepted-row", "status": "accepted-intentional", "owner": "qa"},
            {"fingerprint": "unresolved-row", "status": "unresolved"},
        ]
    }

    resolved_report = apply_audit_resolutions(
        report,
        code_quality_scan=code_quality_scan,
        security_scan=None,
        resolution_ledger=ledger,
    )
    filtered_scan = filter_resolved_code_quality_scan(code_quality_scan, ledger)

    assert resolved_report["status"] == "findings"
    assert resolved_report["resolution"] == {
        "status": "unresolved",
        "total_findings": 1,
        "resolved_findings": 0,
        "unresolved_findings": 1,
        "by_status": {"partially-resolved": 1},
        "entry_by_status": {"accepted-intentional": 1, "unresolved": 1},
    }
    assert resolved_report["findings"][0]["resolution"]["resolved"] is False
    assert filtered_scan is not None
    assert [item["fingerprint"] for item in filtered_scan["findings"]] == ["unresolved-row"]
    assert filtered_scan["summary"]["resolved_findings_excluded"] == 1


def test_audit_finding_disposition_can_resolve_non_scanner_finding() -> None:
    report = {
        "status": "findings",
        "findings": [{"id": "missing-tests"}],
    }
    ledger = {
        "finding_dispositions": [
            {
                "finding_id": "missing-tests",
                "status": "accepted-false-positive",
                "reason": "The repository delegates tests to the host application.",
                "owner": "qa",
            }
        ]
    }

    resolved_report = apply_audit_resolutions(
        report,
        code_quality_scan=None,
        security_scan=None,
        resolution_ledger=ledger,
    )

    assert resolved_report["status"] == "clean"
    assert resolved_report["resolution"]["resolved_findings"] == 1
    assert resolved_report["findings"][0]["resolution"] == {
        "status": "accepted-false-positive",
        "resolved": True,
        "matched_entry_count": 0,
        "unresolved_entry_count": 0,
        "reason": "The repository delegates tests to the host application.",
        "owner": "qa",
    }
