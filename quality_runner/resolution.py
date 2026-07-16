from __future__ import annotations

from collections import Counter
from typing import Any

RESOLVED_STATUSES = frozenset(
    {
        "accepted-intentional",
        "accepted-false-positive",
        "accepted-risk",
        "false-positive",
        "fixed",
        "superseded",
        "superseded-by-current-scan",
    }
)


def apply_audit_resolutions(
    report: dict[str, Any],
    *,
    code_quality_scan: dict[str, Any] | None,
    security_scan: dict[str, Any] | None,
    resolution_ledger: dict[str, Any] | None,
) -> dict[str, Any]:
    findings = report.get("findings")
    if not isinstance(findings, list):
        return report

    entries = _ledger_entries(resolution_ledger)
    dispositions = _finding_dispositions(resolution_ledger)
    annotated: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        annotated.append(
            {
                **finding,
                "resolution": _audit_finding_resolution(
                    finding,
                    entries=entries,
                    dispositions=dispositions,
                    code_quality_scan=code_quality_scan,
                    security_scan=security_scan,
                ),
            }
        )

    raw_status = "findings" if annotated else "clean"
    unresolved = [
        finding
        for finding in annotated
        if not _finding_is_resolved(finding.get("resolution"))
    ]
    return {
        **report,
        "status": "clean" if not unresolved else raw_status,
        "raw_status": raw_status,
        "findings": annotated,
        "resolution": _resolution_summary(annotated),
    }


def filter_resolved_code_quality_scan(
    code_quality_scan: dict[str, Any] | None,
    resolution_ledger: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(code_quality_scan, dict):
        return code_quality_scan
    findings = code_quality_scan.get("findings")
    if not isinstance(findings, list):
        return code_quality_scan

    by_fingerprint = _entries_by_fingerprint(resolution_ledger)
    if not by_fingerprint:
        return code_quality_scan

    active_findings = [
        finding
        for finding in findings
        if not (
            isinstance(finding, dict)
            and isinstance(finding.get("fingerprint"), str)
            and _status_is_resolved(
                by_fingerprint.get(finding["fingerprint"], {}).get("status")
            )
        )
    ]
    if len(active_findings) == len(findings):
        return code_quality_scan
    summary = code_quality_scan.get("summary")
    filtered_summary = dict(summary) if isinstance(summary, dict) else {}
    filtered_summary["total_findings"] = len(active_findings)
    filtered_summary["resolved_findings_excluded"] = len(findings) - len(active_findings)
    return {**code_quality_scan, "summary": filtered_summary, "findings": active_findings}


def unresolved_audit_report(report: dict[str, Any]) -> dict[str, Any]:
    findings = report.get("findings")
    if not isinstance(findings, list):
        return report
    active_findings = [
        finding
        for finding in findings
        if isinstance(finding, dict) and not _finding_is_resolved(finding.get("resolution"))
    ]
    return {
        **report,
        "status": "clean" if not active_findings else "findings",
        "findings": active_findings,
    }


def resolved_planning_inputs(
    audit_report: dict[str, Any],
    code_quality_scan: dict[str, Any] | None,
    resolution_ledger: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    return (
        unresolved_audit_report(audit_report),
        filter_resolved_code_quality_scan(code_quality_scan, resolution_ledger),
    )


def _audit_finding_resolution(
    finding: dict[str, Any],
    *,
    entries: list[dict[str, Any]],
    dispositions: dict[str, dict[str, Any]],
    code_quality_scan: dict[str, Any] | None,
    security_scan: dict[str, Any] | None,
) -> dict[str, Any]:
    finding_id = finding.get("id")
    fingerprints = _audit_finding_fingerprints(
        finding,
        code_quality_scan=code_quality_scan,
        security_scan=security_scan,
    )
    direct = dispositions.get(finding_id) if isinstance(finding_id, str) else None
    if direct is not None and _disposition_applies(direct, fingerprints):
        return _record_resolution(direct, matched_entry_count=0)

    matched = [
        entry
        for entry in entries
        if isinstance(entry.get("fingerprint"), str)
        and entry["fingerprint"] in fingerprints
    ]
    if not matched:
        return {
            "status": "unresolved",
            "resolved": False,
            "matched_entry_count": 0,
            "unresolved_entry_count": 0,
        }

    statuses = [
        str(entry.get("status"))
        for entry in matched
        if isinstance(entry.get("status"), str) and entry.get("status")
    ]
    unresolved_count = sum(not _status_is_resolved(status) for status in statuses)
    if unresolved_count:
        status = "partially-resolved" if unresolved_count < len(matched) else "unresolved"
        return {
            "status": status,
            "resolved": False,
            "matched_entry_count": len(matched),
            "unresolved_entry_count": unresolved_count,
            "by_status": dict(sorted(Counter(statuses).items())),
        }

    representative = matched[0]
    status = statuses[0] if len(set(statuses)) == 1 else "resolved"
    return {
        **_record_resolution(representative, matched_entry_count=len(matched)),
        "status": status,
        "resolved": True,
        "by_status": dict(sorted(Counter(statuses).items())),
    }


def _audit_finding_fingerprints(
    finding: dict[str, Any],
    *,
    code_quality_scan: dict[str, Any] | None,
    security_scan: dict[str, Any] | None,
) -> set[str]:
    finding_id = finding.get("id")
    if not isinstance(finding_id, str):
        return set()

    fingerprints: set[str] = set()
    raw_findings = code_quality_scan.get("findings") if isinstance(code_quality_scan, dict) else None
    if isinstance(raw_findings, list):
        for raw in raw_findings:
            if not isinstance(raw, dict):
                continue
            category = raw.get("category")
            rule_id = raw.get("rule_id")
            fingerprint = raw.get("fingerprint")
            if (
                isinstance(category, str)
                and isinstance(rule_id, str)
                and isinstance(fingerprint, str)
                and finding_id == f"structural-{category}-{rule_id}"
            ):
                fingerprints.add(fingerprint)

    candidates = security_scan.get("candidates") if isinstance(security_scan, dict) else None
    if isinstance(candidates, list) and finding_id.startswith("security-candidate-"):
        candidate_key = finding_id.removeprefix("security-candidate-").lower()
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidate_id = candidate.get("id")
            fingerprint = candidate.get("fingerprint")
            if (
                isinstance(candidate_id, str)
                and candidate_id.lower() == candidate_key
                and isinstance(fingerprint, str)
            ):
                fingerprints.add(fingerprint)

    return fingerprints


def _resolution_summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    finding_status_counts: Counter[str] = Counter()
    entry_status_counts: Counter[str] = Counter()
    for finding in findings:
        resolution = finding.get("resolution")
        if not isinstance(resolution, dict):
            continue
        status = resolution.get("status")
        if isinstance(status, str) and status:
            finding_status_counts[status] += 1
        by_status = resolution.get("by_status")
        if isinstance(by_status, dict):
            for status, count in by_status.items():
                if isinstance(status, str) and isinstance(count, int) and count > 0:
                    entry_status_counts[status] += count
    resolved_count = sum(
        _finding_is_resolved(finding.get("resolution")) for finding in findings
    )
    unresolved_count = len(findings) - resolved_count
    return {
        "status": "resolved" if unresolved_count == 0 else "unresolved",
        "total_findings": len(findings),
        "resolved_findings": resolved_count,
        "unresolved_findings": unresolved_count,
        "by_status": dict(sorted(finding_status_counts.items())),
        "entry_by_status": dict(sorted(entry_status_counts.items())),
    }


def _record_resolution(record: dict[str, Any], *, matched_entry_count: int) -> dict[str, Any]:
    status = record.get("status")
    resolved = _status_is_resolved(status)
    resolution: dict[str, Any] = {
        "status": status if isinstance(status, str) and status else "unresolved",
        "resolved": resolved,
        "matched_entry_count": matched_entry_count,
        "unresolved_entry_count": 0 if resolved else matched_entry_count,
    }
    for field in ("reason", "owner", "expires", "source", "gate_run_id"):
        value = record.get(field)
        if isinstance(value, str) and value:
            resolution[field] = value
    return resolution


def _disposition_applies(record: dict[str, Any], current_fingerprints: set[str]) -> bool:
    fingerprints = record.get("fingerprints")
    if not isinstance(fingerprints, list) or not fingerprints:
        return True
    return bool(current_fingerprints.intersection(item for item in fingerprints if isinstance(item, str)))


def _finding_is_resolved(value: object) -> bool:
    return isinstance(value, dict) and value.get("resolved") is True


def _status_is_resolved(status: object) -> bool:
    return isinstance(status, str) and status in RESOLVED_STATUSES


def _ledger_entries(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(ledger, dict):
        return []
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _entries_by_fingerprint(ledger: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return {
        entry["fingerprint"]: entry
        for entry in _ledger_entries(ledger)
        if isinstance(entry.get("fingerprint"), str) and entry.get("fingerprint")
    }


def _finding_dispositions(ledger: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(ledger, dict):
        return {}
    records = ledger.get("finding_dispositions")
    if not isinstance(records, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        finding_id = record.get("finding_id")
        if isinstance(finding_id, str) and finding_id:
            indexed[finding_id] = record
    return indexed
