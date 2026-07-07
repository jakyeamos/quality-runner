from __future__ import annotations

import re
from typing import Any


def wiring_decision_slices(code_quality_scan: dict[str, Any] | None) -> list[dict[str, Any]]:
    findings = _integrate_findings(code_quality_scan)
    if not findings:
        return []

    groups: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        groups.setdefault(str(finding["file"]), []).append(finding)

    return [
        _slice_for_wiring_group(file=path, findings=group) for path, group in sorted(groups.items())
    ]


def _integrate_findings(code_quality_scan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(code_quality_scan, dict):
        return []
    findings = code_quality_scan.get("findings")
    if not isinstance(findings, list):
        return []

    normalized: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if finding.get("category") != "integrate":
            continue
        finding_id = finding.get("id")
        severity = finding.get("severity")
        file = finding.get("file")
        line = finding.get("line")
        rule_id = finding.get("rule_id")
        fingerprint = finding.get("fingerprint")
        verification = finding.get("verification")
        score = finding.get("score")
        if (
            isinstance(finding_id, str)
            and finding_id
            and isinstance(severity, str)
            and severity
            and isinstance(file, str)
            and file
            and isinstance(line, int)
            and isinstance(rule_id, str)
            and rule_id
            and isinstance(fingerprint, str)
            and fingerprint
            and isinstance(verification, str)
            and verification
        ):
            normalized.append(
                {
                    "id": finding_id,
                    "severity": severity,
                    "category": "structural:integrate",
                    "summary": f"{rule_id} at {file}:{line}",
                    "file": file,
                    "line": line,
                    "rule_id": rule_id,
                    "fingerprint": fingerprint,
                    "verification": verification,
                    "score": score if isinstance(score, int) else 0,
                    "actionability": "needs-author-decision",
                    "actionability_rationale": (
                        "Unwired or partial work needs an explicit wire, finish, descope, or WIP decision."
                    ),
                }
            )
    return normalized


def _slice_for_wiring_group(*, file: str, findings: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_findings = sorted(
        findings,
        key=lambda finding: (str(finding["rule_id"]), int(finding["line"]), str(finding["id"])),
    )
    finding_ids = [str(finding["id"]) for finding in sorted_findings]
    verification = sorted(
        {str(finding["verification"]) for finding in sorted_findings if finding.get("verification")}
    )
    score = sum(int(finding.get("score") or 0) for finding in sorted_findings)
    return {
        "id": f"decide-wiring-{_path_slug(file)}",
        "title": f"Decide wiring for partial work in {file}",
        "priority": "medium",
        "implementation_allowed": False,
        "disposition_required": True,
        "findings": [
            {
                "id": finding["id"],
                "severity": finding["severity"],
                "category": finding["category"],
                "summary": finding["summary"],
                "file": finding["file"],
                "line": finding["line"],
                "rule_id": finding["rule_id"],
                "fingerprint": finding["fingerprint"],
                "actionability": finding["actionability"],
                "actionability_rationale": finding["actionability_rationale"],
            }
            for finding in sorted_findings
        ],
        "actions": [
            "Review evidence and choose one disposition for this work unit.",
            "Do not delete or prune by default; unwired work may be intentional WIP.",
            "Record the disposition in resolution-ledger.json with owner and rationale.",
        ],
        "action_groups": [
            {
                "class": "wire",
                "finding_ids": finding_ids,
                "actions": [
                    "Connect the capability to a product entrypoint such as a router, CLI, MCP registry, UI route, or public API surface.",
                    "Add an integration test or focused smoke check proving the wired path works.",
                ],
            },
            {
                "class": "finish",
                "finding_ids": finding_ids,
                "actions": [
                    "Complete the implementation and remove stub, placeholder, or NotImplemented paths.",
                    "Run the focused verification command for the touched files.",
                ],
            },
            {
                "class": "descope",
                "finding_ids": finding_ids,
                "actions": [
                    "Remove the partial surface area intentionally only after confirming it is out of scope.",
                    "Document why the scope was cut in the relevant handoff, issue, or truth file.",
                ],
            },
            {
                "class": "accept-wip",
                "finding_ids": finding_ids,
                "actions": [
                    "Record an accepted-intentional disposition with owner, reason, and optional expiry.",
                    "Ensure the WIP is visible through an issue link, handoff note, or truth-file note.",
                ],
            },
        ],
        "verification_gates": [
            *[
                f"After wiring or finishing, run focused verification for {file}: {command}"
                for command in verification[:2]
            ],
            "After accept-wip, record the disposition via gate-respond record-disposition or resolution-ledger evidence.",
            "Rerun quality-runner and confirm the integrate findings clear or are dispositioned with evidence.",
        ],
        "score": score,
    }


def _path_slug(path: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-").lower()
    return slug or "root"
