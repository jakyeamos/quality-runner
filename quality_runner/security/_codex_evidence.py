"""Normalization and validation for Codex Security evidence snapshots."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from quality_runner.evidence_contract import (
    QUALITY_EVIDENCE_SCHEMA,
    normalize_quality_finding,
    validate_quality_finding,
)
from quality_runner.schema_constants import CODEX_SECURITY_EVIDENCE_SCHEMA
from quality_runner.security._codex_common import (
    _FINGERPRINT_KEYS,
    _HEX_64,
    _ID_KEYS,
    _RULE_KEYS,
    _SEVERITY_KEYS,
    _STATUS_KEYS,
    _SUMMARY_KEYS,
    _drop_none_values,
    _evidence_items,
    _evidence_summary,
    _first_text,
    _metadata,
    _normal_key,
    _normal_text,
    _normalize_coverage,
    _normalize_locations,
    _normalize_repository,
    _normalize_revision,
    _normalize_source,
    _quality_level,
    _raw_coverage,
    _validate_coverage,
    _validation_result,
    canonical_hash,
    canonical_json,
)


def import_codex_evidence(source: Mapping[str, Any] | Sequence[Any]) -> dict[str, Any]:
    """Normalize a Codex Security report into the Quality Runner evidence contract."""

    if isinstance(source, Mapping) and source.get("schema") == CODEX_SECURITY_EVIDENCE_SCHEMA:
        validation = validate_codex_evidence(dict(source))
        if not validation["passed"]:
            raise ValueError("invalid Codex evidence: " + "; ".join(validation["errors"]))
        return json.loads(canonical_json(source))

    raw: dict[str, Any]
    if isinstance(source, Mapping):
        raw = json.loads(canonical_json(source))
    elif isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
        raw = {"findings": json.loads(canonical_json(list(source)))}
    else:
        raise ValueError("Codex Security input must be a JSON object or finding list")

    raw_findings = _extract_findings(raw)
    findings = [_normalize_finding(item) for item in raw_findings]
    primary_keys = [str(finding["match_key"]) for finding in findings]
    if len(primary_keys) != len(set(primary_keys)):
        raise ValueError("Codex Security input contains duplicate deterministic finding keys")

    coverage = _normalize_coverage(_raw_coverage(raw))
    repository = _normalize_repository(raw)
    revision = _normalize_revision(raw)
    source_descriptor = _normalize_source(raw)
    artifact: dict[str, Any] = {
        "schema": CODEX_SECURITY_EVIDENCE_SCHEMA,
        "contract_schema": QUALITY_EVIDENCE_SCHEMA,
        "source": source_descriptor,
        "repository": repository,
        "revision": revision,
        "run_id": _first_text(raw, ("run_id", "scan_id", "report_id")),
        "coverage": coverage,
        "coverage_complete": coverage["complete"],
        "findings": sorted(findings, key=lambda finding: str(finding["match_key"])),
        "summary": _evidence_summary(findings, coverage),
    }
    artifact = _drop_none_values(artifact)
    artifact["source_hash"] = canonical_hash(raw)
    artifact["evidence_hash"] = canonical_hash(artifact, exclude=("source_hash", "evidence_hash"))
    return artifact


def validate_codex_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one normalized Codex evidence artifact."""

    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(payload, Mapping):
        errors.append("Codex evidence must be a JSON object")
        return _validation_result(payload, errors=errors, warnings=warnings)
    if payload.get("schema") != CODEX_SECURITY_EVIDENCE_SCHEMA:
        errors.append("Codex evidence schema is invalid")
    if payload.get("contract_schema") != QUALITY_EVIDENCE_SCHEMA:
        errors.append("Codex evidence contract_schema must be quality-evidence-v0.1")
    if not isinstance(payload.get("source"), Mapping):
        errors.append("Codex evidence source descriptor is required")
    elif payload["source"].get("provider") != "codex-security":
        errors.append("Codex evidence source provider must be codex-security")
    _validate_coverage(payload.get("coverage"), errors)

    findings = payload.get("findings")
    primary_keys: list[str] = []
    if not isinstance(findings, list):
        errors.append("Codex evidence findings must be a list")
        findings = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"finding {index} must be an object")
            continue
        quality_result = validate_quality_finding(finding)
        errors.extend(f"finding {index}: {issue}" for issue in quality_result["issues"])
        match_key = finding.get("match_key")
        if not isinstance(match_key, str) or not match_key.strip():
            errors.append(f"finding {index}: match_key is required")
        else:
            primary_keys.append(match_key)
        aliases = finding.get("match_keys")
        if not isinstance(aliases, list) or not all(isinstance(item, str) for item in aliases):
            errors.append(f"finding {index}: match_keys must be a string list")
        if not isinstance(finding.get("fingerprint"), str):
            errors.append(f"finding {index}: fingerprint is required")
    if len(primary_keys) != len(set(primary_keys)):
        errors.append("Codex evidence contains duplicate match_key values")

    for field in ("source_hash", "evidence_hash"):
        value = payload.get(field)
        if not isinstance(value, str) or not _HEX_64.fullmatch(value):
            errors.append(f"Codex evidence {field} must be a lowercase SHA-256 hash")
    if isinstance(payload.get("evidence_hash"), str):
        expected = canonical_hash(payload, exclude=("source_hash", "evidence_hash"))
        if payload["evidence_hash"] != expected:
            errors.append("Codex evidence evidence_hash does not match the artifact contents")

    if payload.get("coverage_complete") is not None:
        coverage = payload.get("coverage")
        if isinstance(coverage, Mapping) and payload["coverage_complete"] != coverage.get(
            "complete"
        ):
            errors.append("Codex evidence coverage_complete disagrees with coverage.complete")
    if (
        not primary_keys
        and isinstance(payload.get("coverage"), Mapping)
        and payload["coverage"].get("complete") is False
    ):
        warnings.append("empty Codex evidence has incomplete coverage")
    return _validation_result(payload, errors=errors, warnings=warnings)


def deterministic_finding_key(finding: Mapping[str, Any]) -> str:
    """Return the primary deterministic key for a Codex-style finding."""

    existing = finding.get("match_key")
    if isinstance(existing, str) and existing.strip():
        return existing
    return _finding_aliases(finding)[0]


def _extract_findings(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    if isinstance(raw.get("runs"), list):
        findings: list[dict[str, Any]] = []
        for run in raw["runs"]:
            if not isinstance(run, Mapping) or not isinstance(run.get("results"), list):
                continue
            for result in run["results"]:
                if isinstance(result, Mapping):
                    findings.append(_sarif_finding(result))
        return findings
    for key in ("findings", "vulnerabilities", "issues", "alerts", "results", "evidence"):
        value = raw.get(key)
        if isinstance(value, list):
            return [
                dict(item) if isinstance(item, Mapping) else {"summary": str(item)}
                for item in value
            ]
        if value is not None:
            raise ValueError(f"Codex Security {key} must be a list")
    if any(key in raw for key in (*_RULE_KEYS, *_SUMMARY_KEYS)):
        return [dict(raw)]
    return []


def _sarif_finding(result: Mapping[str, Any]) -> dict[str, Any]:
    message = result.get("message")
    summary = message.get("text") if isinstance(message, Mapping) else message
    fingerprints = result.get("fingerprints") or result.get("partialFingerprints")
    fingerprint = None
    if isinstance(fingerprints, Mapping):
        for key in sorted(fingerprints):
            if str(fingerprints[key]).strip():
                fingerprint = str(fingerprints[key])
                break
    locations = result.get("locations")
    return {
        "id": result.get("ruleId") or result.get("id"),
        "rule_id": result.get("ruleId"),
        "severity": result.get("level"),
        "summary": summary or result.get("ruleId") or "Codex Security finding",
        "locations": locations if isinstance(locations, list) else [],
        "fingerprint": fingerprint,
        "evidence": result.get("properties") or [],
        "status": result.get("state") or "open",
    }


def _normalize_finding(raw: Mapping[str, Any]) -> dict[str, Any]:
    source = dict(raw)
    provider_id = _first_text(source, _ID_KEYS)
    fingerprint = _first_text(source, _FINGERPRINT_KEYS)
    rule_id = _first_text(source, _RULE_KEYS) or "codex-security"
    summary = _first_text(source, _SUMMARY_KEYS) or f"Codex Security finding for {rule_id}"
    severity = _first_text(source, _SEVERITY_KEYS) or "unknown"
    locations = _normalize_locations(source)
    aliases = _finding_aliases(
        {
            "provider_finding_id": provider_id,
            "fingerprint": fingerprint,
            "rule_id": rule_id,
            "summary": summary,
            "locations": locations,
        }
    )
    match_key = aliases[0]
    finding_id = provider_id or match_key
    metadata = _metadata(source)
    metadata.update(
        {
            "provider": "codex-security",
            "match_key": match_key,
            "match_keys": aliases,
            "locations": locations,
            "severity": severity,
        }
    )
    normalized = normalize_quality_finding(
        finding_id=finding_id,
        criterion_id=rule_id,
        criterion_title=_first_text(source, ("criterion_title", "title", "name")) or rule_id,
        criterion_scope="security",
        level=_quality_level(source),
        summary=summary,
        evidence=_evidence_items(source, summary, locations),
        metadata=metadata,
        source="codex-security",
    )
    normalized.update(
        {
            "provider": "codex-security",
            "provider_finding_id": provider_id,
            "fingerprint": fingerprint or f"codex-{canonical_hash(aliases[-1])[:24]}",
            "match_key": match_key,
            "match_keys": aliases,
            "locations": locations,
            "severity": severity,
            "status": _first_text(source, _STATUS_KEYS) or "open",
        }
    )
    return _drop_none_values(normalized)


def _finding_aliases(finding: Mapping[str, Any]) -> list[str]:
    explicit_key = _first_text(finding, ("match_key", "stable_key", "stable_id"))
    fingerprint = _first_text(finding, ("fingerprint",))
    provider_id = _first_text(
        finding, ("provider_finding_id", "finding_id", "alert_id", "uuid", "id")
    )
    semantic = canonical_hash(
        {
            "rule": _normal_text(_first_text(finding, _RULE_KEYS) or "codex-security"),
            "summary": _normal_text(_first_text(finding, _SUMMARY_KEYS) or ""),
            "paths": sorted(
                str(location.get("file", ""))
                for location in _normalize_locations(finding)
                if location.get("file")
            ),
        }
    )[:32]
    aliases: list[str] = []
    if explicit_key:
        aliases.append(f"key:{_normal_key(explicit_key)}")
    if fingerprint:
        aliases.append(f"fingerprint:{_normal_key(fingerprint)}")
    if provider_id:
        aliases.append(f"provider:{_normal_key(provider_id)}")
    aliases.append(f"semantic:{semantic}")
    return list(dict.fromkeys(aliases))
