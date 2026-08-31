from __future__ import annotations

from typing import Any, cast


def analysis_evidence_findings(
    code_quality_scan: dict[str, Any] | None,
    *,
    agent_review_mode: str | None,
) -> list[dict[str, Any]]:
    if not isinstance(code_quality_scan, dict):
        return []

    findings: list[dict[str, Any]] = []
    deferred_checks = _dict_items(code_quality_scan.get("deferred_checks"))
    if code_quality_scan.get("coverage") == "partial" or deferred_checks:
        check_names = sorted(
            {
                check
                for item in deferred_checks
                if isinstance((check := item.get("check")), str) and check
            }
        )
        evidence = [
            f"{item.get('check')}: {item.get('reason')}"
            for item in deferred_checks
            if isinstance(item.get("check"), str) and isinstance(item.get("reason"), str)
        ]
        findings.append(
            {
                "id": "analysis-coverage-partial",
                "severity": "warning",
                "category": "analysis:coverage",
                "summary": "Quality analysis coverage is partial.",
                "evidence": evidence or ["code-quality-scan.json reports coverage=partial."],
                "recommended_fix": (
                    "Run an explicit full analysis refresh and resolve any unavailable analysis "
                    "prerequisites before treating the audit as complete."
                ),
                "verification": [
                    "Rerun quality-runner with full analysis enabled.",
                    "Confirm code-quality-scan.json reports coverage=full and no deferred checks.",
                ],
                "owner": None,
                "score": max(100, len(check_names) * 100),
            }
        )

    summary_value: object = code_quality_scan.get("summary")
    summary = cast(dict[str, Any], summary_value) if isinstance(summary_value, dict) else {}
    scan_budget = summary.get("scan_budget")
    if (
        isinstance(scan_budget, dict)
        and cast(dict[str, Any], scan_budget).get("budget_exceeded") is True
    ):
        scan_budget = cast(dict[str, Any], scan_budget)
        skipped = scan_budget.get("skipped_text_files")
        skipped_count = skipped if isinstance(skipped, int) and not isinstance(skipped, bool) else 0
        findings.append(
            {
                "id": "analysis-scan-budget-exceeded",
                "severity": "warning",
                "category": "analysis:coverage",
                "summary": "The code-quality scan stopped at its text-file budget.",
                "evidence": [
                    f"Configured text-file budget: {scan_budget.get('max_text_files')}.",
                    f"Scanned text files: {scan_budget.get('scanned_text_files')}.",
                    f"Text files skipped by the budget: {skipped_count}.",
                ],
                "recommended_fix": (
                    "Increase or remove the scan budget, narrow the intended scope explicitly, "
                    "or split the repository into complete declared scan scopes."
                ),
                "verification": [
                    "Rerun quality-runner over the intended scope.",
                    "Confirm summary.scan_budget.budget_exceeded is false and no files were skipped by the scan budget.",
                ],
                "owner": None,
                "score": max(500, skipped_count * 10),
            }
        )

    findings.extend(
        _skill_review_obligation_findings(
            _dict_items(code_quality_scan.get("skill_coverage")),
            agent_review_mode=agent_review_mode,
        )
    )
    return findings


def package_manager_preflight_findings(
    package_manager_preflight: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(package_manager_preflight, dict):
        return []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for warning in _dict_items(package_manager_preflight.get("warnings")):
        code = warning.get("code")
        if isinstance(code, str) and code:
            grouped.setdefault(code, []).append(warning)

    findings: list[dict[str, Any]] = []
    for code, warnings in sorted(grouped.items()):
        evidence = sorted(
            {
                f"{_string_or_default(warning.get('path'), '.')}: "
                f"{_string_or_default(warning.get('message'), code)}"
                for warning in warnings
            }
        )
        findings.append(
            {
                "id": f"package-preflight-{code.replace('_', '-')}",
                "severity": "warning",
                "category": "package-manager",
                "summary": _string_or_default(warnings[0].get("message"), code),
                "evidence": evidence,
                "recommended_fix": (
                    "Reconcile package-manager declarations and lockfiles so every detected "
                    "workspace has one consistent, present lockfile."
                ),
                "verification": [
                    "Rerun quality-runner after reconciling package-manager state.",
                    f"Confirm package-manager-preflight.json no longer contains warning {code}.",
                ],
                "owner": None,
                "score": len(warnings) * 400,
            }
        )
    return findings


def _skill_review_obligation_findings(
    coverage: list[dict[str, Any]],
    *,
    agent_review_mode: str | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    statuses = [("review_rejected", "warning", "quality-skill-review-rejected")]
    if agent_review_mode != "off":
        statuses.append(
            (
                "review_required",
                "observation",
                (
                    "quality-skill-review-required"
                    if agent_review_mode == "required"
                    else "quality-skill-review-pending"
                ),
            )
        )
    for status, severity, finding_id in statuses:
        obligations = [item for item in coverage if item.get("status") == status]
        if not obligations:
            continue
        evidence = sorted(
            {
                f"{_string_or_default(item.get('skill_id'), 'unknown-skill')}:"
                f"{_string_or_default(item.get('rule_id'), 'unknown-review')} ({status})"
                for item in obligations
            }
        )
        if len(evidence) > 10:
            evidence = [
                *evidence[:10],
                f"{len(evidence) - 10} additional review obligations omitted.",
            ]
        rejected = status == "review_rejected"
        pending = status == "review_required" and agent_review_mode != "required"
        findings.append(
            {
                "id": finding_id,
                "severity": severity,
                "category": "skill:agent-review",
                "summary": (
                    f"{len(obligations)} code-quality agent review obligation"
                    f"{'s were' if len(obligations) != 1 else ' was'} "
                    f"{'rejected' if rejected else 'queued' if pending else 'not completed'}."
                ),
                "evidence": evidence,
                "recommended_fix": (
                    "Correct and resubmit the rejected skill review report."
                    if rejected
                    else "Complete the selected skill reviews and provide the review report to Quality Runner."
                ),
                "verification": [
                    "Rerun quality-runner with a valid skill review report.",
                    f"Confirm no skill coverage entry remains in status {status}.",
                ],
                "owner": None,
                "score": len(obligations) * (300 if rejected else 100),
            }
        )
    return findings


def _dict_items(value: object) -> list[dict[str, Any]]:
    return (
        [cast(dict[str, Any], item) for item in cast(list[object], value) if isinstance(item, dict)]
        if isinstance(value, list)
        else []
    )


def _string_or_default(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default
