from __future__ import annotations

import re
from typing import Any

from quality_runner.code_quality_findings import CATEGORY_ORDER


def structural_cluster_slices(code_quality_scan: dict[str, Any] | None) -> list[dict[str, Any]]:
    code_findings = _code_quality_findings(code_quality_scan)
    if not code_findings:
        return []

    groups: dict[str, list[dict[str, Any]]] = {}
    for finding in code_findings:
        groups.setdefault(finding["file"], []).append(finding)

    return [
        _slice_for_structural_cluster(file=path, findings=cluster)
        for path, cluster in sorted(groups.items())
    ]


def _code_quality_findings(code_quality_scan: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(code_quality_scan, dict):
        return []
    findings = code_quality_scan.get("findings")
    if not isinstance(findings, list):
        return []

    normalized: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding_id = finding.get("id")
        category = finding.get("category")
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
            and isinstance(category, str)
            and category
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
                    "category": category,
                    "severity": severity,
                    "file": file,
                    "line": line,
                    "rule_id": rule_id,
                    "fingerprint": fingerprint,
                    "verification": verification,
                    "score": score if isinstance(score, int) else 0,
                }
            )
    return normalized


def _slice_for_structural_cluster(*, file: str, findings: list[dict[str, Any]]) -> dict[str, Any]:
    cluster_findings = sorted(
        findings,
        key=lambda finding: (
            _category_rank(str(finding["category"])),
            str(finding["rule_id"]),
            int(finding["line"]),
        ),
    )
    score = sum(int(finding.get("score") or 0) for finding in cluster_findings)
    verification = sorted(
        {
            str(finding["verification"])
            for finding in cluster_findings
            if finding.get("verification")
        }
    )
    return {
        "id": f"remediate-structural-{_path_slug(file)}",
        "title": f"Remediate structural cluster in {file}",
        "priority": _structural_cluster_priority(cluster_findings),
        "implementation_allowed": False,
        "findings": [
            {
                "id": finding["id"],
                "severity": finding["severity"],
                "category": f"structural:{finding['category']}",
                "summary": f"{finding['rule_id']} at {finding['file']}:{finding['line']}",
                "file": finding["file"],
                "line": finding["line"],
                "rule_id": finding["rule_id"],
                "fingerprint": finding["fingerprint"],
            }
            for finding in cluster_findings
        ],
        "actions": [
            f"Review {len(cluster_findings)} current structural findings in {file} as one advisory cluster.",
            (
                "Make one coherent external remediation batch only if the rows share a "
                "behavior-preserving change."
            ),
            (
                "Rerun quality-runner and confirm the listed fingerprints clear or are "
                "dispositioned with evidence."
            ),
        ],
        "verification_gates": [
            *[f"Run focused verification for {file}: {command}" for command in verification[:2]],
            (
                "Rerun quality-runner and compare code-quality-scan.json plus "
                "resolution-ledger.json for this cluster."
            ),
        ],
        "score": score,
    }


def _structural_cluster_priority(findings: list[dict[str, Any]]) -> str:
    if any(finding.get("severity") in {"critical", "blocker"} for finding in findings):
        return "high"
    if any(finding.get("severity") == "warning" for finding in findings):
        return "medium"
    return "low"


def _path_slug(path: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-").lower()
    return slug or "root"


def _category_rank(category: str) -> int:
    return CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else len(CATEGORY_ORDER)
