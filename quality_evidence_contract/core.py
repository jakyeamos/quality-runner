from __future__ import annotations

from typing import Any, Literal

QUALITY_EVIDENCE_SCHEMA = "quality-evidence-v0.1"
QUALITY_FINDING_SCHEMA = "quality-finding-v0.1"
FindingLevel = Literal["pass", "info", "warning", "blocker", "error", "critical"]
FINDING_LEVELS: frozenset[str] = frozenset(
    {"pass", "info", "warning", "blocker", "error", "critical"}
)
BLOCKING_LEVELS: frozenset[str] = frozenset({"blocker", "error", "critical"})


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def normalize_evidence_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            normalized.append(
                {
                    "schema": QUALITY_EVIDENCE_SCHEMA,
                    "kind": "text",
                    "summary": item,
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or item.get("reason") or item.get("file") or "").strip()
        evidence = {
            "schema": QUALITY_EVIDENCE_SCHEMA,
            "kind": str(item.get("kind", "structured")),
            "summary": summary,
        }
        for key in ("file", "line_start", "line_end", "snippet", "reason", "command", "status"):
            if key in item and item[key] is not None:
                evidence[key] = item[key]
        normalized.append(evidence)
    return normalized


def normalize_quality_finding(
    *,
    finding_id: str | None = None,
    criterion_id: str,
    criterion_title: str = "",
    criterion_scope: str = "",
    level: str,
    summary: str,
    evidence: object = None,
    metadata: dict[str, Any] | None = None,
    source: str = "",
) -> dict[str, Any]:
    normalized_level = level if level in FINDING_LEVELS else "warning"
    return {
        "schema": QUALITY_FINDING_SCHEMA,
        "finding_id": finding_id,
        "criterion_id": criterion_id,
        "criterion_title": criterion_title,
        "criterion_scope": criterion_scope,
        "level": normalized_level,
        "blocking": normalized_level in BLOCKING_LEVELS,
        "summary": summary,
        "evidence": normalize_evidence_items(evidence),
        "evidence_text": _string_list(evidence),
        "metadata": metadata or {},
        "source": source,
    }


def validate_quality_finding(finding: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    if finding.get("schema") != QUALITY_FINDING_SCHEMA:
        issues.append("quality finding schema is invalid")
    if not str(finding.get("criterion_id", "")).strip():
        issues.append("quality finding criterion_id is required")
    if finding.get("level") not in FINDING_LEVELS:
        issues.append("quality finding level is invalid")
    if not str(finding.get("summary", "")).strip():
        issues.append("quality finding summary is required")
    if not isinstance(finding.get("evidence"), list):
        issues.append("quality finding evidence must be a list")
    return {"passed": not issues, "issues": issues}


def quality_finding_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "pass": sum(1 for finding in findings if finding.get("level") == "pass"),
        "warning": sum(1 for finding in findings if finding.get("level") == "warning"),
        "blocker": sum(
            1 for finding in findings if finding.get("level") in {"blocker", "error", "critical"}
        ),
    }
