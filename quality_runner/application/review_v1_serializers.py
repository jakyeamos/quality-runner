from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NotRequired, TypedDict, cast

from quality_runner.application.review_v1_reports import (
    REVIEW_REPORT_SCHEMA as _REVIEW_REPORT_SCHEMA,
)
from quality_runner.application.review_v1_reports import (
    review_report_from_v1 as _review_report_from_v1,
)
from quality_runner.application.review_v1_reports import review_report_to_v1 as _review_report_to_v1
from quality_runner.core.review_contracts import (
    EvidenceReference,
    FreshnessPolicy,
    ReviewBreadth,
    ReviewManifest,
    ReviewMode,
    ReviewPacket,
    ReviewScope,
)

REVIEW_CONTEXT_SCHEMA = "quality-runner-review-context-v0.1"
REVIEW_MANIFEST_SCHEMA = "quality-runner-review-manifest-v0.1"
REVIEW_REPORT_SCHEMA = _REVIEW_REPORT_SCHEMA
review_report_from_v1 = _review_report_from_v1
review_report_to_v1 = _review_report_to_v1
_MODES = ("task", "blind", "combined")
_SCOPES = ("task", "project")
_BREADTHS = ("focused", "related", "full")
_CONTEXT_KEYS = frozenset(
    {
        "schema",
        "run_id",
        "repo_root",
        "mode",
        "scope",
        "breadth",
        "task",
        "repository_state",
        "changed_files",
        "exclusions",
        "evidence",
        "omitted_evidence",
        "known_issues",
        "previous_summary",
        "freshness",
        "input_hashes",
        "packets",
    }
)
_MANIFEST_KEYS = frozenset(
    {
        "schema",
        "run_id",
        "mode",
        "scope",
        "breadth",
        "exclusions",
        "evidence_references",
        "freshness",
        "input_hashes",
        "artifact_paths",
    }
)
_EVIDENCE_KEYS = frozenset({"path", "kind", "available", "note"})
_FRESHNESS_KEYS = frozenset(
    {
        "new_invocation_required",
        "prior_review_context_included",
        "previous_agent_summary_included",
        "hidden_reasoning_included",
        "active_cycle",
    }
)


class V1ReviewPacket(TypedDict):
    schema: str
    run_id: str
    repo_root: str
    mode: ReviewMode
    scope: ReviewScope
    breadth: ReviewBreadth
    exclusions: list[str]
    evidence: list[EvidenceReference]
    omitted_evidence: list[str]
    freshness: FreshnessPolicy
    input_hashes: dict[str, str]
    task: NotRequired[str]
    repository_state: NotRequired[dict[str, object]]
    changed_files: NotRequired[list[str]]
    known_issues: NotRequired[list[str]]
    previous_summary: NotRequired[str]
    packets: NotRequired[list[V1ReviewPacket]]


type ReviewPacketProjection = ReviewPacket | V1ReviewPacket


def review_packet_to_v1(packet: ReviewPacketProjection) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": packet["schema"],
        "run_id": packet["run_id"],
        "repo_root": packet["repo_root"],
        "mode": packet["mode"],
        "scope": packet["scope"],
        "breadth": packet["breadth"],
        "exclusions": list(packet["exclusions"]),
        "evidence": [_evidence_to_v1(item) for item in packet["evidence"]],
        "omitted_evidence": list(packet["omitted_evidence"]),
        "freshness": _freshness_to_v1(packet["freshness"]),
        "input_hashes": dict(packet["input_hashes"]),
    }
    legacy_packet = cast(V1ReviewPacket, packet)
    if "task" in legacy_packet:
        payload["task"] = legacy_packet["task"]
    if "repository_state" in legacy_packet:
        payload["repository_state"] = dict(legacy_packet["repository_state"])
    if "changed_files" in legacy_packet:
        payload["changed_files"] = list(legacy_packet["changed_files"])
    if "known_issues" in legacy_packet:
        payload["known_issues"] = list(legacy_packet["known_issues"])
    if "previous_summary" in legacy_packet:
        payload["previous_summary"] = legacy_packet["previous_summary"]
    if "packets" in legacy_packet:
        payload["packets"] = [review_packet_to_v1(child) for child in legacy_packet["packets"]]
    return payload


def review_packet_from_v1(payload: Mapping[str, object]) -> V1ReviewPacket:
    _reject_extra_keys(payload, _CONTEXT_KEYS, "review context")
    _expect_schema(payload, REVIEW_CONTEXT_SCHEMA)
    packet: V1ReviewPacket = {
        "schema": _string(payload, "schema"),
        "run_id": _string(payload, "run_id"),
        "repo_root": _string(payload, "repo_root"),
        "mode": _mode(payload, "mode"),
        "scope": _scope(payload, "scope"),
        "breadth": _breadth(payload, "breadth"),
        "exclusions": _string_list(payload, "exclusions"),
        "evidence": _evidence_list(payload, "evidence"),
        "omitted_evidence": _string_list(payload, "omitted_evidence"),
        "freshness": _freshness_from_v1(_object(payload, "freshness")),
        "input_hashes": _string_mapping(payload, "input_hashes", nonempty_values=True),
    }
    _apply_legacy_packet_fields(packet, payload)
    if "packets" in payload:
        packet["packets"] = [
            review_packet_from_v1(_object_value(item, "packets"))
            for item in _sequence(payload, "packets")
        ]
    return packet


def review_manifest_to_v1(manifest: ReviewManifest) -> dict[str, object]:
    return {
        "schema": manifest["schema"],
        "run_id": manifest["run_id"],
        "mode": manifest["mode"],
        "scope": manifest["scope"],
        "breadth": manifest["breadth"],
        "exclusions": list(manifest["exclusions"]),
        "evidence_references": [_evidence_to_v1(item) for item in manifest["evidence_references"]],
        "freshness": _freshness_to_v1(manifest["freshness"]),
        "input_hashes": dict(manifest["input_hashes"]),
        "artifact_paths": dict(manifest["artifact_paths"]),
    }


def review_manifest_from_v1(payload: Mapping[str, object]) -> ReviewManifest:
    _reject_extra_keys(payload, _MANIFEST_KEYS, "review manifest")
    _expect_schema(payload, REVIEW_MANIFEST_SCHEMA)
    return {
        "schema": _string(payload, "schema"),
        "run_id": _string(payload, "run_id"),
        "mode": _mode(payload, "mode"),
        "scope": _scope(payload, "scope"),
        "breadth": _breadth(payload, "breadth"),
        "exclusions": _string_list(payload, "exclusions"),
        "evidence_references": _evidence_list(payload, "evidence_references"),
        "freshness": _freshness_from_v1(_object(payload, "freshness")),
        "input_hashes": _string_mapping(payload, "input_hashes", nonempty_values=True),
        "artifact_paths": _string_mapping(payload, "artifact_paths"),
    }


def _evidence_to_v1(reference: EvidenceReference) -> dict[str, object]:
    return {
        "path": reference["path"],
        "kind": reference["kind"],
        "available": reference["available"],
        "note": reference["note"],
    }


def _apply_legacy_packet_fields(packet: V1ReviewPacket, payload: Mapping[str, object]) -> None:
    if "task" in payload:
        packet["task"] = _string(payload, "task")
    if "repository_state" in payload:
        packet["repository_state"] = dict(_object(payload, "repository_state"))
    if "changed_files" in payload:
        packet["changed_files"] = _string_list(payload, "changed_files")
    if "known_issues" in payload:
        packet["known_issues"] = _string_list(payload, "known_issues")
    if "previous_summary" in payload:
        packet["previous_summary"] = _string(payload, "previous_summary")


def _freshness_to_v1(policy: FreshnessPolicy) -> dict[str, object]:
    return {
        "new_invocation_required": policy["new_invocation_required"],
        "prior_review_context_included": policy["prior_review_context_included"],
        "previous_agent_summary_included": policy["previous_agent_summary_included"],
        "hidden_reasoning_included": policy["hidden_reasoning_included"],
        "active_cycle": policy["active_cycle"],
    }


def _evidence_list(payload: Mapping[str, object], key: str) -> list[EvidenceReference]:
    return [_evidence_from_v1(_object_value(item, key)) for item in _sequence(payload, key)]


def _evidence_from_v1(payload: Mapping[str, object]) -> EvidenceReference:
    _reject_extra_keys(payload, _EVIDENCE_KEYS, "evidence")
    available = payload.get("available")
    if not isinstance(available, bool):
        raise ValueError("evidence available must be a boolean")
    return {
        "path": _string(payload, "path"),
        "kind": _string(payload, "kind"),
        "available": available,
        "note": _text(payload, "note"),
    }


def _freshness_from_v1(payload: Mapping[str, object]) -> FreshnessPolicy:
    _reject_extra_keys(payload, _FRESHNESS_KEYS, "freshness")
    new_invocation_required = payload.get("new_invocation_required")
    prior_review_context_included = payload.get("prior_review_context_included")
    previous_agent_summary_included = payload.get("previous_agent_summary_included")
    hidden_reasoning_included = payload.get("hidden_reasoning_included")
    active_cycle = payload.get("active_cycle")
    if (
        new_invocation_required is not True
        or prior_review_context_included is not False
        or hidden_reasoning_included is not False
        or not isinstance(previous_agent_summary_included, bool)
        or not isinstance(active_cycle, bool)
    ):
        raise ValueError("freshness values must be booleans")
    return {
        "new_invocation_required": new_invocation_required,
        "prior_review_context_included": prior_review_context_included,
        "previous_agent_summary_included": previous_agent_summary_included,
        "hidden_reasoning_included": hidden_reasoning_included,
        "active_cycle": active_cycle,
    }


def _expect_schema(payload: Mapping[str, object], expected: str) -> None:
    if payload.get("schema") != expected:
        raise ValueError(f"expected schema {expected}")


def _reject_extra_keys(payload: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    extra = sorted(set(payload) - allowed)
    if extra:
        raise ValueError(f"{label} contains unsupported fields: {', '.join(extra)}")


def _object(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    return _object_value(payload.get(key), key)


def _object_value(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _sequence(payload: Mapping[str, object], key: str) -> Sequence[object]:
    value = payload.get(key)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{key} must be an array")
    return value


def _string(payload: Mapping[str, object], key: str) -> str:
    value = _text(payload, key)
    if not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _string_list(
    payload: Mapping[str, object], key: str, *, nonempty_values: bool = False
) -> list[str]:
    values = _sequence(payload, key)
    if not all(isinstance(value, str) and (not nonempty_values or bool(value)) for value in values):
        raise ValueError(f"{key} must contain strings")
    return list(cast(Sequence[str], values))


def _string_mapping(
    payload: Mapping[str, object], key: str, *, nonempty_values: bool = False
) -> dict[str, str]:
    value = _object(payload, key)
    if not all(
        isinstance(item, str) and (not nonempty_values or bool(item)) for item in value.values()
    ):
        raise ValueError(f"{key} must map strings to strings")
    return {name: cast(str, item) for name, item in value.items()}


def _mode(payload: Mapping[str, object], key: str) -> ReviewMode:
    value = _string(payload, key)
    if value not in _MODES:
        raise ValueError(f"invalid mode: {value}")
    return cast(ReviewMode, value)


def _scope(payload: Mapping[str, object], key: str) -> ReviewScope:
    value = _string(payload, key)
    if value not in _SCOPES:
        raise ValueError(f"invalid scope: {value}")
    return cast(ReviewScope, value)


def _breadth(payload: Mapping[str, object], key: str) -> ReviewBreadth:
    value = _string(payload, key)
    if value not in _BREADTHS:
        raise ValueError(f"invalid breadth: {value}")
    return cast(ReviewBreadth, value)
