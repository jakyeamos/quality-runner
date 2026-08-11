from __future__ import annotations

import json
from pathlib import Path

from quality_runner.resolution import (
    apply_audit_resolutions,
    filter_resolved_code_quality_scan,
)


def _ledger_finding() -> dict[str, object]:
    return {
        "fingerprint": "accepted-row",
        "category": "harden",
        "severity": "warning",
        "rule_id": "explicit-any",
        "file": "src/example.py",
        "line": 3,
        "score": 2,
        "confidence": "high",
        "verification": "run tests",
    }


def test_resolution_ledger_does_not_inherit_latest_run_without_explicit_baseline(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality_ledger import build_resolution_ledger

    previous = tmp_path / ".quality-runner" / "runs" / "old-run"
    previous.mkdir(parents=True)
    (previous / "resolution-ledger.json").write_text(
        json.dumps({"entries": [{**_ledger_finding(), "status": "accepted-intentional"}]}),
        encoding="utf-8",
    )

    ledger = build_resolution_ledger(
        repo_root=tmp_path,
        run_id="fresh-run",
        code_quality_scan={"findings": [_ledger_finding()]},
        config={},
    )

    assert ledger["entries"][0]["status"] == "unresolved"
    assert ledger["disposition_provenance"] == {
        "mode": "none",
        "previous_run_id": None,
        "source": None,
    }


def test_resolution_ledger_explicit_baseline_and_reset_are_provenanced(tmp_path: Path) -> None:
    from quality_runner.code_quality_ledger import build_resolution_ledger

    previous = tmp_path / ".quality-runner" / "runs" / "baseline"
    previous.mkdir(parents=True)
    (previous / "resolution-ledger.json").write_text(
        json.dumps({"entries": [{**_ledger_finding(), "status": "accepted-intentional"}]}),
        encoding="utf-8",
    )
    kwargs = {
        "repo_root": tmp_path,
        "run_id": "current",
        "code_quality_scan": {"findings": [_ledger_finding()]},
        "config": {},
    }

    inherited = build_resolution_ledger(**kwargs, previous_run_id="baseline")
    reset = build_resolution_ledger(
        **kwargs,
        previous_run_id="baseline",
        reset_previous_dispositions=True,
    )

    assert inherited["entries"][0]["status"] == "accepted-intentional"
    assert inherited["entries"][0]["disposition_run_id"] == "baseline"
    assert reset["entries"][0]["status"] == "unresolved"
    assert reset["disposition_provenance"]["mode"] == "reset"


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
