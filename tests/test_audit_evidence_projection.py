from __future__ import annotations

from quality_runner.audit import build_audit_report
from quality_runner.findings import validate_audit_report


def test_audit_projects_incomplete_scan_and_preflight_evidence_as_findings() -> None:
    report = build_audit_report(
        scan={"run_id": "projection", "repo_root": "/repo"},
        standards_packet={"profile": "default", "config": {}, "requirements": []},
        capability_map={"available": [], "missing": [], "warnings": []},
        security_scan={
            "settings": {"enabled": True},
            "candidates": [],
            "agent_review_gates": [],
            "missing_capabilities": [
                {
                    "id": "security_dependency_audit",
                    "type": "evidence",
                    "capability_kind": "evidence",
                    "status": "missing",
                    "required_by": "security-baseline",
                    "reason": "dependency manifest present but no vulnerability audit gate detected",
                    "recommended_commands": ["pip-audit"],
                }
            ],
        },
        code_quality_scan={
            "findings": [],
            "coverage": "partial",
            "deferred_checks": [
                {
                    "check": "architecture",
                    "reason": "global analysis is deferred until an explicit full refresh",
                }
            ],
            "summary": {
                "scan_budget": {
                    "budget_exceeded": True,
                    "max_text_files": 100,
                    "scanned_text_files": 100,
                    "skipped_text_files": 7,
                }
            },
            "skill_coverage": [
                {
                    "skill_id": "architecture-maintainability",
                    "rule_id": "architecture-review",
                    "status": "review_required",
                },
                {
                    "skill_id": "pr-risk",
                    "rule_id": "risk-review",
                    "status": "review_rejected",
                },
            ],
        },
        package_manager_preflight={
            "status": "warning",
            "warnings": [
                {
                    "code": "missing_nested_package_manager_lockfile",
                    "message": "Declared workspace lockfile is missing.",
                    "path": "apps/admin/pnpm-lock.yaml",
                },
                {
                    "code": "missing_nested_package_manager_lockfile",
                    "message": "Declared workspace lockfile is missing.",
                    "path": "apps/web/pnpm-lock.yaml",
                },
            ],
        },
        agent_review_mode="required",
    )

    findings = {finding["id"]: finding for finding in report["findings"]}
    assert {
        "analysis-coverage-partial",
        "analysis-scan-budget-exceeded",
        "missing-security-dependency-audit",
        "package-preflight-missing-nested-package-manager-lockfile",
        "quality-skill-review-rejected",
        "quality-skill-review-required",
    } <= findings.keys()
    assert (
        len(findings["package-preflight-missing-nested-package-manager-lockfile"]["evidence"]) == 2
    )
    assert findings["analysis-coverage-partial"]["actionability"] == "informational"
    assert findings["quality-skill-review-required"]["actionability"] == ("needs-author-decision")
    assert validate_audit_report(report)["passed"] is True


def test_audit_does_not_project_complete_or_non_matching_scan_evidence() -> None:
    report = build_audit_report(
        scan={"run_id": "complete", "repo_root": "/repo"},
        standards_packet={"profile": "default", "config": {}, "requirements": []},
        capability_map={"available": [], "missing": [], "warnings": []},
        security_scan={
            "settings": {"enabled": True},
            "candidates": [],
            "agent_review_gates": [],
            "missing_capabilities": [],
        },
        code_quality_scan={
            "findings": [],
            "coverage": "full",
            "deferred_checks": [],
            "summary": {
                "scan_budget": {
                    "budget_exceeded": False,
                    "max_text_files": 100,
                    "scanned_text_files": 20,
                    "skipped_text_files": 0,
                }
            },
            "skill_coverage": [
                {
                    "skill_id": "architecture-maintainability",
                    "rule_id": "architecture-rule",
                    "status": "evaluated",
                },
                {
                    "skill_id": "pr-risk",
                    "rule_id": "risk-rule",
                    "status": "no_matching_files",
                },
                {
                    "skill_id": "test-strategy",
                    "rule_id": "test-review",
                    "status": "review_required",
                },
            ],
        },
        package_manager_preflight={"status": "ok", "warnings": []},
        agent_review_mode="off",
    )

    assert report["status"] == "clean"
    assert report["findings"] == []
    assert validate_audit_report(report)["passed"] is True
