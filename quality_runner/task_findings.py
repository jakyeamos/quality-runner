from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from fnmatch import fnmatch
from typing import Any

from quality_runner.schema_constants import NORMALIZED_FINDINGS_SCHEMA

CONFIDENCE_SCORE = {"low": 0.33, "medium": 0.66, "high": 1.0}
REQUIRED_PROMOTION_EVIDENCE = {"positive", "negative", "ambiguous"}
DELTA_BUCKETS = (
    "new_enforced",
    "persisted",
    "resolved",
    "waived",
    "advisory",
    "out_of_scope",
    "unknown",
)


def normalize_findings(
    *,
    code_quality_scan: dict[str, Any],
    security_scan: dict[str, Any],
    prevention: dict[str, Any],
) -> dict[str, Any]:
    policies = _rule_policies(prevention)
    occurrences: list[dict[str, Any]] = []
    occurrences.extend(
        _normalize_rows(
            code_quality_scan.get("findings"),
            detector="code_quality",
            coverage_ref="code_quality",
            policies=policies,
        )
    )
    occurrences.extend(
        _normalize_rows(
            security_scan.get("candidates"),
            detector="security",
            coverage_ref="security",
            policies=policies,
            rule_field="category",
            path_field="file",
            severity_field="severity_hint",
        )
    )
    coverage = {
        "code_quality": _coverage_value(code_quality_scan.get("coverage")),
        "security": _coverage_value(security_scan.get("coverage")),
    }
    ambiguities = _ambiguities(occurrences)
    return {
        "schema": NORMALIZED_FINDINGS_SCHEMA,
        "coverage": coverage,
        "occurrences": sorted(occurrences, key=_occurrence_sort_key),
        "ambiguities": ambiguities,
    }


def compare_findings(
    *,
    baseline: dict[str, Any],
    current: dict[str, Any],
    changed_paths: list[str],
    dispositions: list[dict[str, Any]],
    required_modules: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    result: dict[str, list[dict[str, Any]]] = {name: [] for name in DELTA_BUCKETS}
    blockers: list[dict[str, str]] = []
    current_time = now or datetime.now(UTC)
    changed = set(changed_paths)

    for ambiguity in [*baseline.get("ambiguities", []), *current.get("ambiguities", [])]:
        result["unknown"].append(dict(ambiguity))
        blockers.append(
            {
                "code": "ambiguous_occurrence_match",
                "message": str(ambiguity.get("message") or "occurrence matching is ambiguous"),
            }
        )

    baseline_rows = _unique_occurrences(baseline.get("occurrences", []))
    current_rows = _unique_occurrences(current.get("occurrences", []))
    baseline_keys = set(baseline_rows)
    current_keys = set(current_rows)

    for key in sorted(baseline_keys & current_keys):
        result["persisted"].append(current_rows[key])

    for key in sorted(current_keys - baseline_keys):
        occurrence = current_rows[key]
        path = str(occurrence.get("path") or "")
        if path and path not in changed:
            result["out_of_scope"].append(occurrence)
            continue
        waiver = _active_waiver(occurrence, dispositions, current_time)
        if waiver is not None:
            result["waived"].append({**occurrence, "waiver": waiver})
        elif occurrence.get("enforcement_eligible") is True:
            result["new_enforced"].append(occurrence)
        else:
            result["advisory"].append(occurrence)

    current_coverage = current.get("coverage", {})
    for key in sorted(baseline_keys - current_keys):
        occurrence = baseline_rows[key]
        module = str(occurrence.get("coverage_ref") or "")
        if current_coverage.get(module) == "complete":
            result["resolved"].append(occurrence)
        else:
            unknown = {
                **occurrence,
                "unknown_reason": f"{module or 'finding'} coverage is not complete",
            }
            result["unknown"].append(unknown)
            blockers.append(
                {
                    "code": "incomplete_comparable_coverage",
                    "message": unknown["unknown_reason"],
                }
            )

    for module in required_modules:
        status = current_coverage.get(module, "unknown")
        if status != "complete":
            blockers.append(
                {
                    "code": "required_coverage_incomplete",
                    "message": f"required module {module} has {status} coverage",
                }
            )

    return {
        "buckets": {name: sorted(rows, key=_occurrence_sort_key) for name, rows in result.items()},
        "counts": {name: len(rows) for name, rows in result.items()},
        "blockers": _deduplicate_blockers(blockers),
    }


def promotion_issues(prevention: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for rule in prevention.get("rules", []):
        if not isinstance(rule, dict) or rule.get("state") != "behavior-verified":
            continue
        evidence = _evidence_kinds(rule.get("evidence_refs"))
        missing = sorted(REQUIRED_PROMOTION_EVIDENCE - evidence)
        if missing:
            issues.append(
                {
                    "code": "incomplete_rule_promotion_evidence",
                    "message": (
                        f"{rule.get('detector')}:{rule.get('rule_id')} lacks "
                        f"{', '.join(missing)} fixture evidence"
                    ),
                }
            )
    return issues


def _normalize_rows(
    value: object,
    *,
    detector: str,
    coverage_ref: str,
    policies: dict[tuple[str, str], dict[str, Any]],
    rule_field: str = "rule_id",
    path_field: str = "file",
    severity_field: str = "severity",
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        rule_id = row.get(rule_field)
        fingerprint = row.get("fingerprint")
        path = row.get(path_field)
        line = row.get("line")
        confidence = row.get("confidence")
        if (
            not isinstance(rule_id, str)
            or not rule_id
            or not isinstance(fingerprint, str)
            or not fingerprint
            or not isinstance(path, str)
            or not path
        ):
            result.append(
                {
                    "detector": detector,
                    "rule_id": str(rule_id or ""),
                    "fingerprint": str(fingerprint or ""),
                    "source_fingerprint": str(fingerprint or ""),
                    "path": str(path or ""),
                    "line": line if isinstance(line, int) else None,
                    "severity": str(row.get(severity_field) or "unknown"),
                    "confidence": str(confidence or "unknown"),
                    "coverage_ref": coverage_ref,
                    "enforcement_eligible": False,
                    "normalization_error": "missing stable rule, fingerprint, or path",
                }
            )
            continue
        policy = policies.get((detector, rule_id))
        result.append(
            {
                "detector": detector,
                "rule_id": rule_id,
                "fingerprint": fingerprint,
                "source_fingerprint": fingerprint,
                "path": path,
                "line": line if isinstance(line, int) else None,
                "severity": str(row.get(severity_field) or "unknown"),
                "confidence": str(confidence or "unknown"),
                "coverage_ref": coverage_ref,
                "enforcement_eligible": _eligible(policy, path, confidence),
                "evidence": row.get("evidence"),
            }
        )
    return _assign_occurrence_fingerprints(result)


def _assign_occurrence_fingerprints(
    occurrences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    invalid: list[dict[str, Any]] = []
    for occurrence in occurrences:
        if occurrence.get("normalization_error"):
            invalid.append(occurrence)
            continue
        key = (
            str(occurrence["detector"]),
            str(occurrence["rule_id"]),
            str(occurrence["path"]),
            str(occurrence["source_fingerprint"]),
        )
        grouped.setdefault(key, []).append(occurrence)

    normalized = list(invalid)
    for key, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=_source_occurrence_sort_key)
        location_counts: dict[int | None, int] = {}
        for row in ordered:
            line = row.get("line")
            location = line if isinstance(line, int) else None
            location_counts[location] = location_counts.get(location, 0) + 1
        for ordinal, row in enumerate(ordered):
            line = row.get("line")
            location = line if isinstance(line, int) else None
            discriminator = (
                f"ambiguous-location:{location}"
                if location_counts[location] > 1
                else f"ordinal:{ordinal}"
            )
            normalized.append(
                {
                    **row,
                    "fingerprint": _occurrence_fingerprint(*key, discriminator),
                }
            )
    return normalized


def _occurrence_fingerprint(
    detector: str,
    rule_id: str,
    path: str,
    source_fingerprint: str,
    discriminator: str,
) -> str:
    identity = "\0".join((detector, rule_id, path, source_fingerprint, discriminator)).encode()
    return hashlib.sha256(identity).hexdigest()


def _source_occurrence_sort_key(
    item: dict[str, Any],
) -> tuple[int, str, str, str]:
    line = item.get("line")
    return (
        line if isinstance(line, int) else 0,
        str(item.get("evidence") or ""),
        str(item.get("severity") or ""),
        str(item.get("confidence") or ""),
    )


def _rule_policies(prevention: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in prevention.get("rules", []):
        if not isinstance(item, dict):
            continue
        detector = item.get("detector")
        rule_id = item.get("rule_id")
        if isinstance(detector, str) and isinstance(rule_id, str):
            result[(detector, rule_id)] = item
    return result


def _eligible(policy: dict[str, Any] | None, path: str, confidence: object) -> bool:
    if not policy or policy.get("state") != "behavior-verified":
        return False
    if REQUIRED_PROMOTION_EVIDENCE - _evidence_kinds(policy.get("evidence_refs")):
        return False
    patterns = policy.get("paths")
    if (
        isinstance(patterns, list)
        and patterns
        and not any(isinstance(pattern, str) and fnmatch(path, pattern) for pattern in patterns)
    ):
        return False
    threshold = policy.get("confidence_threshold", 0.0)
    score = CONFIDENCE_SCORE.get(str(confidence), 0.0)
    return isinstance(threshold, (int, float)) and score >= float(threshold)


def _evidence_kinds(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item.split(":", 1)[0] for item in value if isinstance(item, str) and ":" in item}


def _ambiguities(occurrences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    ambiguities: list[dict[str, Any]] = []
    for item in occurrences:
        if item.get("normalization_error"):
            ambiguities.append(
                {
                    **item,
                    "message": str(item["normalization_error"]),
                }
            )
            continue
        key = _occurrence_key(item)
        grouped.setdefault(key, []).append(item)
    for key, rows in sorted(grouped.items()):
        if len(rows) > 1:
            ambiguities.append(
                {
                    "fingerprint": key,
                    "message": f"fingerprint {key} identifies {len(rows)} occurrences",
                    "occurrences": rows,
                }
            )
    return ambiguities


def _unique_occurrences(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or item.get("normalization_error"):
            continue
        key = _occurrence_key(item)
        if key in result:
            duplicates.add(key)
        result[key] = item
    for key in duplicates:
        result.pop(key, None)
    return result


def _occurrence_key(item: dict[str, Any]) -> str:
    return f"{item.get('detector')}:{item.get('rule_id')}:{item.get('fingerprint')}"


def _coverage_value(value: object) -> str:
    if value in {"complete", "partial", "unknown"}:
        return str(value)
    if value == "full":
        return "complete"
    return "unknown"


def _active_waiver(
    occurrence: dict[str, Any],
    dispositions: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any] | None:
    for item in dispositions:
        if item.get("fingerprint") != occurrence.get("fingerprint"):
            continue
        if not all(item.get(field) for field in ("owner", "reason", "review_evidence", "expires")):
            continue
        try:
            expiry = datetime.fromisoformat(str(item["expires"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= now:
            continue
        return {
            "owner": item["owner"],
            "reason": item["reason"],
            "evidence": item["review_evidence"],
            "expires": item["expires"],
        }
    return None


def _occurrence_sort_key(item: dict[str, Any]) -> tuple[str, str, int, str]:
    line = item.get("line")
    return (
        str(item.get("path") or ""),
        str(item.get("rule_id") or ""),
        line if isinstance(line, int) else 0,
        str(item.get("fingerprint") or ""),
    )


def _deduplicate_blockers(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"code": code, "message": message}
        for code, message in sorted({(item["code"], item["message"]) for item in items})
    ]
