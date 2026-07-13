from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

from quality_runner.application.review_reporting import build_review_report
from quality_runner.core.review_contracts import (
    CombinedReviewPacket,
    CombinedReviewResponseProvenance,
    ReviewAdapterIdentity,
    ReviewFinding,
    ReviewPacket,
    ReviewReport,
    ReviewResponseMode,
    ReviewResponseProvenance,
)
from quality_runner.core.review_packets import (
    MAX_REVIEW_RESPONSE_BYTES,
    canonical_packet_hash,
    validate_prepared_packet,
)
from quality_runner.core.review_packets import (
    response_template as _response_template,
)
from quality_runner.schema_constants import (
    COMBINED_REVIEW_ADAPTER_RESPONSE_SCHEMA,
    REVIEW_ADAPTER_RESPONSE_SCHEMA,
)

ADAPTER_RESPONSE_SCHEMA = REVIEW_ADAPTER_RESPONSE_SCHEMA
COMBINED_ADAPTER_RESPONSE_SCHEMA = COMBINED_REVIEW_ADAPTER_RESPONSE_SCHEMA
MAX_RAW_OUTPUT_BYTES = MAX_REVIEW_RESPONSE_BYTES

_SINGLE_RESPONSE_KEYS = frozenset(
    {
        "schema",
        "run_id",
        "mode",
        "packet_hash",
        "status",
        "adapter",
        "completed_at",
        "findings",
        "evidence_used",
        "evidence_unavailable",
        "raw_output",
    }
)
_COMBINED_RESPONSE_KEYS = frozenset({"schema", "run_id", "mode", "responses"})
_ADAPTER_KEYS = frozenset({"name", "version", "transport"})
_FINDING_KEYS = frozenset(
    {
        "id",
        "fingerprint",
        "severity",
        "classification",
        "confidence",
        "summary",
        "why_it_matters",
        "location",
        "evidence",
        "recommended_fix",
        "agent_prompt",
        "human_confirmation_required",
        "status",
    }
)


def validate_review_response(
    payload: Mapping[str, object],
    context: ReviewPacket,
) -> tuple[ReviewReport, ReviewResponseProvenance | CombinedReviewResponseProvenance]:
    """Validate a response against its prepared context before normalizing findings."""
    validate_prepared_packet(context)
    mode = context["mode"]
    if mode == "combined":
        combined = cast(CombinedReviewPacket, context)
        return _validate_combined_response(payload, combined)
    return _validate_single_response(payload, context)


def response_template(context: ReviewPacket) -> dict[str, object]:
    """Return a strictly shaped local-file response template for a prepared packet."""
    return _response_template(context)


def canonical_response_digest(payload: Mapping[str, object]) -> str:
    serialized = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_combined_response(
    payload: Mapping[str, object],
    context: CombinedReviewPacket,
) -> tuple[ReviewReport, CombinedReviewResponseProvenance]:
    _reject_extra_keys(payload, _COMBINED_RESPONSE_KEYS, "combined adapter response")
    if payload.get("schema") != COMBINED_ADAPTER_RESPONSE_SCHEMA:
        raise ValueError(f"expected schema {COMBINED_ADAPTER_RESPONSE_SCHEMA}")
    if _text(payload, "run_id") != context["run_id"]:
        raise ValueError("adapter response run_id does not match the prepared review")
    if _text(payload, "mode") != "combined":
        raise ValueError("combined adapter response mode must be combined")
    values = _objects(payload, "responses")
    if len(values) != 2:
        raise ValueError("combined adapter response requires exactly task and blind responses")
    child_by_mode = {packet["mode"]: packet for packet in context["packets"]}
    response_by_mode: dict[str, tuple[ReviewReport, ReviewResponseProvenance]] = {}
    for value in values:
        mode = _text(value, "mode")
        child = child_by_mode.get(mode)
        if child is None:
            raise ValueError("combined adapter response contains an unexpected child mode")
        if mode in response_by_mode:
            raise ValueError("combined adapter response contains duplicate child modes")
        response_by_mode[mode] = _validate_single_response(value, child)
    if set(response_by_mode) != {"task", "blind"}:
        raise ValueError("combined adapter response requires one task and one blind response")
    task_report, task_provenance = response_by_mode["task"]
    blind_report, blind_provenance = response_by_mode["blind"]
    findings = _merge_findings(task_report["findings"], blind_report["findings"])
    report = build_review_report(
        run_id=context["run_id"],
        mode="combined",
        scope=context["scope"],
        breadth=context["breadth"],
        findings=findings,
        evidence_used=[*task_report["evidence_used"], *blind_report["evidence_used"]],
        evidence_unavailable=[
            *task_report["evidence_unavailable"],
            *blind_report["evidence_unavailable"],
            "Task and blind responses were validated independently and grouped locally.",
        ],
        exclusions=context["exclusions"],
        adapter_status="review-complete",
        task_provenance="None",
    )
    return report, {
        "schema": COMBINED_ADAPTER_RESPONSE_SCHEMA,
        "run_id": context["run_id"],
        "mode": "combined",
        "responses": [task_provenance, blind_provenance],
        "response_digest": canonical_response_digest(payload),
    }


def _validate_single_response(
    payload: Mapping[str, object], context: ReviewPacket
) -> tuple[ReviewReport, ReviewResponseProvenance]:
    _reject_extra_keys(payload, _SINGLE_RESPONSE_KEYS, "adapter response")
    if payload.get("schema") != ADAPTER_RESPONSE_SCHEMA:
        raise ValueError(f"expected schema {ADAPTER_RESPONSE_SCHEMA}")
    mode = context["mode"]
    if mode not in {"task", "blind"}:
        raise ValueError("single adapter response requires a task or blind packet")
    if _text(payload, "run_id") != context["run_id"]:
        raise ValueError("adapter response run_id does not match the prepared review")
    if _text(payload, "mode") != mode:
        raise ValueError("adapter response mode does not match the prepared review")
    expected_hash = _packet_hash(context)
    if _text(payload, "packet_hash") != expected_hash:
        raise ValueError("adapter response packet_hash does not match the prepared review")
    if _text(payload, "status") != "review-complete":
        raise ValueError("adapter response status must be review-complete")
    adapter = _adapter_identity(_object(payload, "adapter"))
    completed_at = _timestamp(payload, "completed_at")
    findings = _findings(payload)
    report = build_review_report(
        run_id=context["run_id"],
        mode=mode,
        scope=context["scope"],
        breadth=context["breadth"],
        findings=findings,
        evidence_used=_strings(payload, "evidence_used"),
        evidence_unavailable=_strings(payload, "evidence_unavailable"),
        exclusions=context["exclusions"],
        adapter_status="review-complete",
        task_provenance=_task_provenance(context),
    )
    _reject_duplicate_findings(report["findings"])
    raw_output = payload.get("raw_output")
    if raw_output is not None:
        if not isinstance(raw_output, str):
            raise ValueError("adapter response raw_output must be a string")
        if len(raw_output.encode("utf-8")) > MAX_REVIEW_RESPONSE_BYTES:
            raise ValueError("adapter response raw_output exceeds the local size limit")
    return report, {
        "schema": ADAPTER_RESPONSE_SCHEMA,
        "run_id": context["run_id"],
        "mode": cast(ReviewResponseMode, mode),
        "packet_hash": expected_hash,
        "completed_at": completed_at,
        "adapter": adapter,
        "response_digest": canonical_response_digest(payload),
    }


def _merge_findings(
    task_findings: Sequence[ReviewFinding], blind_findings: Sequence[ReviewFinding]
) -> list[ReviewFinding]:
    merged: list[ReviewFinding] = []
    fingerprints: set[str] = set()
    ids: set[str] = set()
    for finding in [*task_findings, *blind_findings]:
        if finding["id"] in ids and finding["fingerprint"] not in fingerprints:
            raise ValueError("combined responses reuse a finding id for different findings")
        if finding["fingerprint"] in fingerprints:
            continue
        ids.add(finding["id"])
        fingerprints.add(finding["fingerprint"])
        merged.append(finding)
    return merged


def _reject_duplicate_findings(findings: Sequence[ReviewFinding]) -> None:
    ids = [finding["id"] for finding in findings]
    fingerprints = [finding["fingerprint"] for finding in findings]
    if len(ids) != len(set(ids)):
        raise ValueError("adapter response contains duplicate finding ids")
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("adapter response contains duplicate finding fingerprints")


def _task_provenance(context: ReviewPacket) -> str | None:
    if context["mode"] == "blind":
        return None
    task_hash = context["input_hashes"].get("task")
    if not isinstance(task_hash, str) or not task_hash:
        raise ValueError("task review context requires a task provenance hash")
    return task_hash


def _packet_hash(context: ReviewPacket) -> str:
    return canonical_packet_hash(context)


def _adapter_identity(payload: Mapping[str, object]) -> ReviewAdapterIdentity:
    _reject_extra_keys(payload, _ADAPTER_KEYS, "adapter identity")
    transport = _text(payload, "transport")
    if transport != "local-file":
        raise ValueError("adapter transport must be local-file")
    return {
        "name": _text(payload, "name"),
        "version": _text(payload, "version"),
        "transport": "local-file",
    }


def _timestamp(payload: Mapping[str, object], key: str) -> str:
    value = _text(payload, key)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{key} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{key} must include a timezone")
    return value


def _reject_extra_keys(payload: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    extra = sorted(set(payload) - allowed)
    if extra:
        raise ValueError(f"{label} contains unsupported fields: {', '.join(extra)}")


def _object(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _objects(payload: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"{key} must be an array of objects")
    return [item for item in value if isinstance(item, Mapping)]


def _findings(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    findings = _objects(payload, "findings")
    for finding in findings:
        _reject_extra_keys(finding, _FINDING_KEYS, "adapter finding")
    return findings


def _strings(payload: Mapping[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{key} must be an array of non-empty strings")
    return [item.strip() for item in value]


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
