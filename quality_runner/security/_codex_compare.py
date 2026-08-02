"""Coverage-aware comparison for normalized Codex Security evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from quality_runner.evidence_contract import QUALITY_EVIDENCE_SCHEMA
from quality_runner.schema_constants import (
    CODEX_SECURITY_COMPARE_SCHEMA,
    CODEX_SECURITY_EVIDENCE_SCHEMA,
)
from quality_runner.security._codex_common import (
    canonical_hash,
    canonical_json,
    normalize_coverage,
    normalize_path,
    validation_result,
)
from quality_runner.security._codex_evidence import (
    finding_aliases,
    import_codex_evidence,
    validate_codex_evidence,
)


def compare_codex_evidence(
    baseline: Mapping[str, Any] | Sequence[Any],
    current: Mapping[str, Any] | Sequence[Any],
    *,
    follow_up_coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare two reports using stable aliases and coverage-aware disappearance."""

    baseline_artifact = _ensure_evidence(baseline)
    current_artifact = _ensure_evidence(current)
    if follow_up_coverage is not None:
        current_artifact = _with_follow_up_coverage(current_artifact, follow_up_coverage)

    baseline_validation = validate_codex_evidence(baseline_artifact)
    current_validation = validate_codex_evidence(current_artifact)
    if not baseline_validation["passed"]:
        raise ValueError(
            "invalid baseline Codex evidence: " + "; ".join(baseline_validation["errors"])
        )
    if not current_validation["passed"]:
        raise ValueError(
            "invalid current Codex evidence: " + "; ".join(current_validation["errors"])
        )

    matches, summary = _comparison_projection(baseline_artifact, current_artifact)
    comparison: dict[str, Any] = {
        "schema": CODEX_SECURITY_COMPARE_SCHEMA,
        "contract_schema": QUALITY_EVIDENCE_SCHEMA,
        "baseline": baseline_artifact,
        "current": current_artifact,
        "baseline_hash": baseline_artifact["evidence_hash"],
        "current_hash": current_artifact["evidence_hash"],
        "input_hashes": {
            "baseline": baseline_artifact["evidence_hash"],
            "current": current_artifact["evidence_hash"],
        },
        "coverage": current_artifact["coverage"],
        "matches": matches,
        "summary": summary,
        "implementation_allowed": False,
    }
    comparison["comparison_hash"] = canonical_hash(comparison, exclude=("comparison_hash",))
    return comparison


def validate_codex_compare(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a comparison, including both hash-bound evidence snapshots."""

    errors: list[str] = []
    warnings: list[str] = []
    if payload.get("schema") != CODEX_SECURITY_COMPARE_SCHEMA:
        errors.append("Codex comparison schema is invalid")
    if payload.get("contract_schema") != QUALITY_EVIDENCE_SCHEMA:
        errors.append("Codex comparison contract_schema is invalid")
    baseline = _dict(payload.get("baseline"))
    current = _dict(payload.get("current"))
    if baseline is None or current is None:
        errors.append("Codex comparison must include baseline and current evidence")
    else:
        for label, artifact in (("baseline", baseline), ("current", current)):
            result = validate_codex_evidence(artifact)
            errors.extend(f"{label}: {error}" for error in result["errors"])
            warnings.extend(f"{label}: {warning}" for warning in result["warnings"])
            if payload.get(f"{label}_hash") != artifact.get("evidence_hash"):
                errors.append(f"Codex comparison {label}_hash is not bound to {label} evidence")
        input_hashes = payload.get("input_hashes")
        if not isinstance(input_hashes, Mapping):
            errors.append("Codex comparison input_hashes are required")
        else:
            input_hashes_map = cast(Mapping[str, Any], input_hashes)
            if input_hashes_map.get("baseline") != payload.get("baseline_hash"):
                errors.append("Codex comparison input_hashes.baseline is not bound")
            if input_hashes_map.get("current") != payload.get("current_hash"):
                errors.append("Codex comparison input_hashes.current is not bound")
        expected_matches, expected_summary = _comparison_projection(baseline, current)
        if canonical_json(payload.get("matches")) != canonical_json(expected_matches):
            errors.append(
                "Codex comparison matches are not a deterministic projection of its inputs"
            )
        if canonical_json(payload.get("summary")) != canonical_json(expected_summary):
            errors.append(
                "Codex comparison summary is not a deterministic projection of its inputs"
            )
        if canonical_json(payload.get("coverage")) != canonical_json(current.get("coverage")):
            errors.append("Codex comparison coverage is not bound to current evidence")
    matches = payload.get("matches")
    if not isinstance(matches, list):
        errors.append("Codex comparison matches must be a list")
    else:
        for index, match in enumerate(_dict_list(cast(object, matches))):
            if match.get("status") not in {"present", "new", "resolved", "unknown"}:
                errors.append(f"comparison match {index} has an invalid status")
            if not isinstance(match.get("match_key"), str) or not match["match_key"].strip():
                errors.append(f"comparison match {index} requires match_key")
    if payload.get("implementation_allowed") is not False:
        errors.append("Codex comparison implementation_allowed must remain false")
    if isinstance(payload.get("comparison_hash"), str):
        expected = canonical_hash(payload, exclude=("comparison_hash",))
        if payload["comparison_hash"] != expected:
            errors.append("Codex comparison comparison_hash does not match the artifact contents")
    else:
        errors.append("Codex comparison comparison_hash is required")
    return validation_result(payload, errors=errors, warnings=warnings)


def _ensure_evidence(value: Mapping[str, Any] | Sequence[Any]) -> dict[str, Any]:
    if isinstance(value, Mapping) and value.get("schema") == CODEX_SECURITY_EVIDENCE_SCHEMA:
        artifact = json.loads(canonical_json(value))
    else:
        artifact = import_codex_evidence(value)
    return artifact


def _with_follow_up_coverage(
    artifact: Mapping[str, Any], follow_up_coverage: Mapping[str, Any]
) -> dict[str, Any]:
    updated = json.loads(canonical_json(artifact))
    updated["coverage"] = normalize_coverage(follow_up_coverage)
    updated["coverage_complete"] = updated["coverage"]["complete"]
    updated["evidence_hash"] = canonical_hash(updated, exclude=("source_hash", "evidence_hash"))
    return updated


def _comparison_projection(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    baseline_findings = _finding_map(baseline["findings"])
    current_findings = _finding_map(current["findings"])
    pairs, unmatched_baseline, unmatched_current = _pair_findings(
        baseline_findings, current_findings
    )
    coverage_complete = _follow_up_coverage_complete(
        baseline,
        current,
        unmatched_baseline,
    )

    matches: list[dict[str, Any]] = []
    for baseline_finding, current_finding in pairs:
        matches.append(
            _comparison_match(
                status="present",
                baseline_finding=baseline_finding,
                current_finding=current_finding,
                reason="finding matched by a deterministic provider or semantic key",
            )
        )
    for finding in unmatched_current:
        matches.append(
            _comparison_match(
                status="new",
                baseline_finding=None,
                current_finding=finding,
                reason="finding has no deterministic match in the baseline",
            )
        )
    for finding in unmatched_baseline:
        status = "resolved" if coverage_complete else "unknown"
        reason = (
            "finding disappeared and follow-up coverage is complete"
            if coverage_complete
            else "finding disappeared but follow-up coverage is incomplete"
        )
        matches.append(
            _comparison_match(
                status=status,
                baseline_finding=finding,
                current_finding=None,
                reason=reason,
            )
        )
    matches.sort(key=lambda match: (str(match["match_key"]), str(match["status"])))
    summary = {
        "present": sum(1 for match in matches if match["status"] == "present"),
        "new": sum(1 for match in matches if match["status"] == "new"),
        "resolved": sum(1 for match in matches if match["status"] == "resolved"),
        "unknown": sum(1 for match in matches if match["status"] == "unknown"),
        "disappeared": len(unmatched_baseline),
        "follow_up_coverage_complete": coverage_complete,
        "coverage_status": current["coverage"]["status"],
    }
    return matches, summary


def _finding_map(findings: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for finding in findings:
        key = str(finding["match_key"])
        result[key] = dict(finding)
    return result


def _pair_findings(
    baseline: Mapping[str, dict[str, Any]], current: Mapping[str, dict[str, Any]]
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    current_by_alias: dict[str, list[dict[str, Any]]] = {}
    for finding in current.values():
        for alias in _aliases_for_normalized(finding):
            current_by_alias.setdefault(alias, []).append(finding)
    for candidates in current_by_alias.values():
        candidates.sort(key=lambda finding: str(finding["match_key"]))
    matched_current: set[str] = set()
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    unmatched_baseline: list[dict[str, Any]] = []
    for baseline_finding in sorted(baseline.values(), key=lambda item: str(item["match_key"])):
        candidate_pool: list[dict[str, Any]] = []
        for alias in _aliases_for_normalized(baseline_finding):
            candidate_pool.extend(current_by_alias.get(alias, []))
        candidates = {
            str(candidate["match_key"]): candidate
            for candidate in candidate_pool
            if str(candidate["match_key"]) not in matched_current
        }
        if not candidates:
            unmatched_baseline.append(baseline_finding)
            continue
        candidate = candidates[sorted(candidates)[0]]
        matched_current.add(str(candidate["match_key"]))
        pairs.append((baseline_finding, candidate))
    unmatched_current = [
        finding for key, finding in sorted(current.items()) if key not in matched_current
    ]
    return pairs, unmatched_baseline, unmatched_current


def _aliases_for_normalized(finding: Mapping[str, Any]) -> list[str]:
    aliases = finding.get("match_keys")
    if isinstance(aliases, list) and all(
        isinstance(item, str) for item in cast(list[Any], aliases)
    ):
        return [item for item in cast(list[Any], aliases) if isinstance(item, str)]
    return finding_aliases(finding)


def _comparison_match(
    *,
    status: str,
    baseline_finding: Mapping[str, Any] | None,
    current_finding: Mapping[str, Any] | None,
    reason: str,
) -> dict[str, Any]:
    match_key = _comparison_match_key(baseline_finding, current_finding)
    return {
        "match_key": match_key,
        "status": status,
        "state": status,
        "baseline_finding_id": baseline_finding.get("finding_id") if baseline_finding else None,
        "current_finding_id": current_finding.get("finding_id") if current_finding else None,
        "baseline_fingerprint": baseline_finding.get("fingerprint") if baseline_finding else None,
        "current_fingerprint": current_finding.get("fingerprint") if current_finding else None,
        "reason": reason,
    }


def _comparison_match_key(
    baseline_finding: Mapping[str, Any] | None,
    current_finding: Mapping[str, Any] | None,
) -> str | None:
    if baseline_finding and current_finding:
        if baseline_finding.get("match_key") == current_finding.get("match_key"):
            return str(baseline_finding.get("match_key"))
        shared = set(_aliases_for_normalized(baseline_finding)).intersection(
            _aliases_for_normalized(current_finding)
        )
        for prefix in ("fingerprint:", "provider:", "key:", "semantic:"):
            candidates = sorted(alias for alias in shared if alias.startswith(prefix))
            if candidates:
                return candidates[0]
    selected = current_finding or baseline_finding or {}
    value = selected.get("match_key")
    return str(value) if value is not None else None


def _follow_up_coverage_complete(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
    disappeared: Sequence[Mapping[str, Any]],
) -> bool:
    if not disappeared:
        return bool((_dict(current.get("coverage")) or {}).get("complete"))
    coverage = _dict(current.get("coverage"))
    if coverage is None:
        return False
    if coverage.get("status") != "complete" or coverage.get("complete") is not True:
        return False
    if coverage.get("follow_up_complete") is False:
        return False
    baseline_hash = baseline.get("evidence_hash")
    follow_up_of = coverage.get("follow_up_of") or current.get("follow_up_of")
    if follow_up_of is not None and follow_up_of != baseline_hash:
        return False
    covered_keys = coverage.get("covered_match_keys")
    if isinstance(covered_keys, list) and covered_keys:
        covered = {str(item) for item in _any_list(cast(object, covered_keys))}
        if any(
            not covered.intersection(_aliases_for_normalized(finding)) for finding in disappeared
        ):
            return False
    scope = str(coverage.get("scope", "unknown"))
    if scope in {"repository", "repo", "full", "all"}:
        return True
    covered_paths = {
        normalize_path(str(item))
        for item in _any_list(cast(object, coverage.get("scanned_paths")))
        if str(item).strip()
    }
    if not covered_paths:
        # An explicit complete status is itself a coverage assertion. A
        # path-limited scope still has to name the paths it covered, but an
        # unspecified scope is treated as the producer's complete report.
        return scope == "unknown"
    for finding in disappeared:
        locations = finding.get("locations")
        paths = {
            normalize_path(str(location.get("file")))
            for location in _dict_list(locations)
            if location.get("file")
        }
        if not paths:
            return False
        if paths and not paths.issubset(covered_paths):
            return False
    return True


def _dict(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        cast(dict[str, Any], item) for item in cast(list[Any], value) if isinstance(item, Mapping)
    ]


def _any_list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []
