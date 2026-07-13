from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import cast

from quality_runner.core.review_contracts import CombinedReviewPacket, ReviewPacket
from quality_runner.schema_constants import (
    COMBINED_REVIEW_ADAPTER_RESPONSE_SCHEMA,
    REVIEW_ADAPTER_RESPONSE_SCHEMA,
)

MAX_REVIEW_RESPONSE_BYTES = 2_000_000


def validate_prepared_packet(context: ReviewPacket) -> None:
    """Verify freshness semantics and recompute every packet hash before response use."""
    _validate_packet_shape(context)
    _validate_packet_hashes(context)


def canonical_packet_hash(context: ReviewPacket) -> str:
    payload = dict(context)
    payload.pop("input_hashes", None)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def response_template(context: ReviewPacket) -> dict[str, object]:
    """Create a strict local-file response template for one validated packet."""
    validate_prepared_packet(context)
    if context["mode"] == "combined":
        combined = cast(CombinedReviewPacket, context)
        return {
            "schema": COMBINED_REVIEW_ADAPTER_RESPONSE_SCHEMA,
            "run_id": combined["run_id"],
            "mode": "combined",
            "responses": [_single_template(packet) for packet in combined["packets"]],
        }
    return _single_template(context)


def _single_template(context: ReviewPacket) -> dict[str, object]:
    mode = context["mode"]
    if mode not in {"task", "blind"}:
        raise ValueError("adapter response templates require task or blind packets")
    return {
        "schema": REVIEW_ADAPTER_RESPONSE_SCHEMA,
        "run_id": context["run_id"],
        "mode": mode,
        "packet_hash": canonical_packet_hash(context),
        "status": "review-complete",
        "adapter": {"name": "local-reviewer", "version": "1", "transport": "local-file"},
        "completed_at": "<ISO-8601 UTC timestamp>",
        "findings": [],
        "evidence_used": [],
        "evidence_unavailable": [],
        "raw_output": "",
    }


def _validate_packet_shape(context: ReviewPacket) -> None:
    freshness = context.get("freshness")
    if not isinstance(freshness, Mapping) or (
        freshness.get("new_invocation_required") is not True
        or freshness.get("prior_review_context_included") is not False
        or freshness.get("hidden_reasoning_included") is not False
    ):
        raise ValueError("prepared review context does not meet the freshness contract")
    mode = context.get("mode")
    if mode == "task":
        task = cast(Mapping[str, object], context).get("task")
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task review context requires task text")
        return
    if mode == "blind":
        if "task" in context or "previous_summary" in context:
            raise ValueError("blind review context must not include task or prior summary")
        return
    if mode != "combined":
        raise ValueError("prepared review context has an invalid mode")
    combined = cast(CombinedReviewPacket, context)
    forbidden_parent_fields = (
        "task",
        "previous_summary",
        "known_issues",
        "repository_state",
        "changed_files",
    )
    if any(field in combined for field in forbidden_parent_fields):
        raise ValueError("combined review parent must not contain child-only context")
    packets = combined.get("packets")
    if not isinstance(packets, list) or [packet.get("mode") for packet in packets] != [
        "task",
        "blind",
    ]:
        raise ValueError("combined review context requires independent task and blind packets")
    shared_fields = ("schema", "scope", "breadth", "exclusions", "evidence", "omitted_evidence")
    freshness_fields = (
        "new_invocation_required",
        "prior_review_context_included",
        "hidden_reasoning_included",
        "active_cycle",
    )
    parent_freshness = combined["freshness"]
    if parent_freshness.get("previous_agent_summary_included") is not False:
        raise ValueError("combined review parent must not claim prior summary context")
    for packet in packets:
        if (
            packet.get("run_id") != combined["run_id"]
            or packet.get("repo_root") != combined["repo_root"]
        ):
            raise ValueError("combined review child packet does not match its parent")
        if any(packet.get(field) != combined.get(field) for field in shared_fields):
            raise ValueError("combined review child packet does not match shared parent fields")
        child_freshness = packet.get("freshness")
        if not isinstance(child_freshness, Mapping) or any(
            child_freshness.get(field) != parent_freshness.get(field) for field in freshness_fields
        ):
            raise ValueError("combined review child packet does not match shared freshness")
        _validate_packet_shape(packet)


def _validate_packet_hashes(context: ReviewPacket) -> None:
    input_hashes = context.get("input_hashes")
    if not isinstance(input_hashes, Mapping):
        raise ValueError("prepared review context requires input hashes")
    mode = context["mode"]
    if mode == "combined":
        combined = cast(CombinedReviewPacket, context)
        task_packet, blind_packet = combined["packets"]
        _validate_packet_hashes(task_packet)
        _validate_packet_hashes(blind_packet)
        expected = {
            "task_packet": canonical_packet_hash(task_packet),
            "blind_packet": canonical_packet_hash(blind_packet),
        }
    elif mode == "task":
        task = cast(Mapping[str, object], context).get("task")
        if not isinstance(task, str):
            raise ValueError("task review context requires task text")
        expected = {
            "packet": canonical_packet_hash(context),
            "task": hashlib.sha256(task.encode("utf-8")).hexdigest(),
        }
    else:
        expected = {"packet": canonical_packet_hash(context)}
    if dict(input_hashes) != expected:
        raise ValueError("prepared review context hashes do not match its contents")
