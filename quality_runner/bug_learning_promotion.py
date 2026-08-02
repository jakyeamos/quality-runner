from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from quality_runner.bug_learning_fleet import (
    PROMOTION_CRITERIA_KEYS,
    candidate_contract_hash,
    provenance_hash_matches,
)

PROMOTION_DECISION_SCHEMA = "quality-runner-candidate-promotion-decision-v0.1"
PROMOTION_RECEIPT_SCHEMA = "quality-runner-candidate-promotion-receipt-v0.1"


def candidate_by_id(payload: object, candidate_id: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    typed_payload = cast(dict[str, Any], payload)
    for candidate in _objects(typed_payload.get("candidates")):
        if candidate.get("id") == candidate_id:
            return candidate
    return None


def read_object(path: Path, errors: list[str], *, label: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{label} is missing: {path}")
        return None
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{label} is unreadable or invalid JSON: {error}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label} must be a JSON object")
        return None
    return cast(dict[str, Any], payload)


def promotion_decision_errors(
    decision: dict[str, Any],
    candidate_id: str,
    fleet: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    if decision.get("schema") != PROMOTION_DECISION_SCHEMA:
        errors.append("promotion decision schema is unsupported")
    if decision.get("candidate_id") != candidate_id:
        errors.append("promotion decision candidate_id does not match")
    if decision.get("decision") != "approved":
        errors.append("promotion decision must record explicit approved status")
    for field in ("decided_by", "decided_at", "reason", "fleet_provenance_hash"):
        if not _nonempty_string(decision.get(field)):
            errors.append(f"promotion decision {field} must be a non-empty string")
    if _parse_timestamp(decision.get("decided_at")) is None:
        errors.append("promotion decision decided_at must be timezone-aware ISO-8601")
    if fleet is not None and decision.get("fleet_provenance_hash") != fleet.get("provenance_hash"):
        errors.append("promotion decision is not bound to the supplied fleet evidence")
    return errors


def supported_receipt_errors(
    path: Path,
    *,
    candidate: dict[str, Any],
    candidate_id: str,
) -> list[str]:
    errors: list[str] = []
    receipt = read_object(path, errors, label="promotion receipt")
    if receipt is None:
        return errors
    if receipt.get("schema") != PROMOTION_RECEIPT_SCHEMA:
        errors.append("promotion receipt schema is unsupported")
    if receipt.get("candidate_id") != candidate_id:
        errors.append("promotion receipt candidate_id does not match")
    if receipt.get("candidate_contract_hash") != candidate_contract_hash(candidate):
        errors.append("promotion receipt candidate contract does not match the registry")
    if receipt.get("status") != "supported" or receipt.get("decision") != "approved":
        errors.append("promotion receipt does not record a supported human approval")
    for field in (
        "decided_by",
        "decision_reason",
        "registry_provenance_hash",
        "fleet_provenance_hash",
    ):
        if not _nonempty_string(receipt.get(field)):
            errors.append(f"promotion receipt {field} must be a non-empty string")
    if _parse_timestamp(receipt.get("decided_at")) is None:
        errors.append("promotion receipt decided_at must be timezone-aware ISO-8601")
    criteria = receipt.get("promotion_criteria")
    typed_criteria = cast(dict[str, Any], criteria) if isinstance(criteria, dict) else {}
    if (
        not isinstance(criteria, dict)
        or set(typed_criteria) != PROMOTION_CRITERIA_KEYS
        or any(
            not isinstance(value, dict)
            or cast(dict[str, Any], value).get("passed") is not True
            for value in typed_criteria.values()
        )
    ):
        errors.append("promotion receipt criteria are missing or failed")
    if receipt.get("errors") != []:
        errors.append("promotion receipt contains unresolved validation errors")
    if not provenance_hash_matches(receipt):
        errors.append("promotion receipt provenance hash does not match its content")
    return errors


def _objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        cast(dict[str, Any], item)
        for item in cast(list[Any], value)
        if isinstance(item, dict)
    ]


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
