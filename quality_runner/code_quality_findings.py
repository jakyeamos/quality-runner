from __future__ import annotations

import hashlib
from typing import Any

from quality_runner.security.redaction import redact_secret_like_literals

CATEGORY_ORDER = [
    "harden",
    "simplify",
    "ponytail",
    "clarify",
    "deduplicate",
    "speed",
    "improve-tests",
    "ui_structural",
    "architecture",
    "integrate",
]
CONFIDENCE_WEIGHT = {"high": 3, "medium": 2, "low": 1}
SEVERITY_WEIGHT = {"warning": 3, "observation": 1}


def _finding(
    *,
    category: str,
    severity: str,
    confidence: str,
    file: str,
    line: int,
    rule_id: str,
    evidence: str,
    expected_improvement: str,
    risk: str,
    verification: str,
    remediation_bucket: str,
) -> dict[str, Any]:
    redacted_evidence = redact_secret_like_literals(evidence).strip()
    fingerprint = _fingerprint(rule_id, file, redacted_evidence)
    return {
        "id": "",
        "fingerprint": fingerprint,
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "score": SEVERITY_WEIGHT[severity] * CONFIDENCE_WEIGHT[confidence],
        "file": file,
        "line": line,
        "rule_id": rule_id,
        "evidence": redacted_evidence,
        "expected_improvement": expected_improvement,
        "risk": risk,
        "verification": verification,
        "remediation_bucket": remediation_bucket,
    }


def _fingerprint(rule_id: str, file: str, evidence: str) -> str:
    normalized = " ".join(evidence.strip().split())
    return hashlib.sha256(f"{rule_id}:{file}:{normalized}".encode()).hexdigest()[:16]


def _category_rank(category: str) -> int:
    if category in CATEGORY_ORDER:
        return CATEGORY_ORDER.index(category)
    if category.startswith("skill:"):
        return len(CATEGORY_ORDER)
    return len(CATEGORY_ORDER) + 1


def _finding_sort_key(finding: dict[str, Any]) -> tuple[int, int, str, int, str]:
    return (
        -int(finding["score"]),
        _category_rank(str(finding["category"])),
        str(finding["file"]),
        int(finding["line"]),
        str(finding["rule_id"]),
    )


def _counts(items: list[dict[str, Any]], field: str, keys: list[str]) -> dict[str, int]:
    counts = {key: 0 for key in keys}
    for item in items:
        value = item.get(field)
        if isinstance(value, str):
            counts[value] = counts.get(value, 0) + 1
    return counts
