from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

from quality_runner.bug_learning_fleet import (
    OBSERVATION_CLASSIFICATIONS,
    OBSERVATION_RESULTS,
)
from quality_runner.bug_learning_promotion import supported_receipt_errors
from quality_runner.fleet.contracts import digest

CANDIDATE_REGISTRY_FILE = "quality-runner-candidates.json"
CANDIDATE_REGISTRY_SCHEMA = "quality-runner-candidate-registry-v0.1"
LIFECYCLE_STATUSES = (
    "repository-regression",
    "reusable-candidate",
    "quality-runner-advisory",
    "fleet-observation",
    "required-gate",
)
DISPOSITION_STATUSES = ("repository-only", "duplicate", "not-detectable")
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "repository-regression": {
        "reusable-candidate",
        "repository-only",
        "duplicate",
        "not-detectable",
    },
    "reusable-candidate": {
        "quality-runner-advisory",
        "repository-only",
        "duplicate",
        "not-detectable",
    },
    "quality-runner-advisory": {
        "fleet-observation",
        "repository-only",
        "duplicate",
        "not-detectable",
    },
    "fleet-observation": {
        "required-gate",
        "repository-only",
        "duplicate",
        "not-detectable",
    },
    "required-gate": set(),
    "repository-only": set(),
    "duplicate": set(),
    "not-detectable": set(),
}


def validate_candidate_registry(
    repo_root: Path,
    *,
    registry_path: str = CANDIDATE_REGISTRY_FILE,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    relative = safe_relative_path_value(registry_path)
    if relative is None:
        return _validation_payload(
            root=root,
            path=registry_path,
            errors=["registry path must be a safe repository-relative path"],
        )
    path = root / relative
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _validation_payload(
            root=root,
            path=relative,
            errors=[f"candidate registry is missing: {relative}"],
        )
    except (OSError, json.JSONDecodeError) as error:
        return _validation_payload(
            root=root,
            path=relative,
            errors=[f"candidate registry is unreadable or invalid JSON: {error}"],
        )
    errors = _registry_errors(root, payload)
    payload_mapping = cast(dict[str, Any], payload) if isinstance(payload, dict) else {}
    regressions = objects(payload_mapping.get("regressions"))
    candidates = objects(payload_mapping.get("candidates"))
    return {
        "schema": "quality-runner-candidate-registry-validation-v0.1",
        "status": "passed" if not errors else "rejected",
        "repo_root": str(root),
        "registry_path": relative,
        "registry_schema": payload_mapping.get("schema") or None,
        "regression_count": len(regressions),
        "candidate_count": len(candidates),
        "covered_regression_count": len(_covered_regression_ids(candidates)),
        "errors": errors,
        "registry": payload_mapping or None,
        "provenance_hash": digest(payload_mapping) if payload_mapping else None,
    }


def safe_relative_path_value(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    return value


def objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, dict)]


def _registry_errors(root: Path, payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["candidate registry must be a JSON object"]
    payload = cast(dict[str, Any], payload)
    errors: list[str] = []
    if payload.get("schema") != CANDIDATE_REGISTRY_SCHEMA:
        errors.append("candidate registry schema is unsupported")
    if not _nonempty_string(payload.get("repository")):
        errors.append("repository must be a non-empty string")
    regressions = objects(payload.get("regressions"))
    candidates = objects(payload.get("candidates"))
    if not isinstance(payload.get("regressions"), list):
        errors.append("regressions must be an array")
    if not isinstance(payload.get("candidates"), list):
        errors.append("candidates must be an array")

    regression_ids: set[str] = set()
    for index, regression in enumerate(regressions):
        prefix = f"regressions[{index}]"
        regression_id = regression.get("id")
        if not _stable_id(regression_id):
            errors.append(f"{prefix}.id must be stable kebab-case")
        elif regression_id in regression_ids:
            errors.append(f"{prefix}.id duplicates {regression_id}")
        else:
            regression_ids.add(str(regression_id))
        for field in ("summary", "regression_test", "command", "confirmed_at"):
            if not _nonempty_string(regression.get(field)):
                errors.append(f"{prefix}.{field} must be a non-empty string")
        if _parse_timestamp(regression.get("confirmed_at")) is None:
            errors.append(f"{prefix}.confirmed_at must be timezone-aware ISO-8601")
        if safe_relative_path_value(regression.get("regression_test")) is None:
            errors.append(f"{prefix}.regression_test must be repository-relative")
        elif not (root / str(regression["regression_test"])).is_file():
            errors.append(f"{prefix}.regression_test is missing from the repository")
        if not isinstance(regression.get("provenance"), dict):
            errors.append(f"{prefix}.provenance must be an object")

    candidate_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        prefix = f"candidates[{index}]"
        candidate_id = candidate.get("id")
        if not _stable_id(candidate_id):
            errors.append(f"{prefix}.id must be stable kebab-case")
        elif candidate_id in candidate_ids:
            errors.append(f"{prefix}.id duplicates {candidate_id}")
        else:
            candidate_ids.add(str(candidate_id))
        errors.extend(_candidate_errors(root, candidate, prefix))

    covered = _covered_regression_ids(candidates)
    missing = sorted(regression_ids - covered)
    unknown = sorted(covered - regression_ids)
    if missing:
        errors.append(
            "every confirmed regression must be evaluated; missing candidate coverage: "
            + ", ".join(missing)
        )
    if unknown:
        errors.append("candidate references unknown regressions: " + ", ".join(unknown))
    return errors


def _candidate_errors(root: Path, candidate: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    for field in ("failure_pattern", "cause", "remediation", "owner"):
        if not _nonempty_string(candidate.get(field)):
            errors.append(f"{prefix}.{field} must be a non-empty string")
    for field in (
        "originating_regressions",
        "producer_surfaces",
        "consumer_surfaces",
        "likely_false_positives",
        "provenance",
        "transitions",
    ):
        if not _nonempty_list(candidate.get(field)):
            errors.append(f"{prefix}.{field} must be a non-empty array")
    for field in (
        "originating_regressions",
        "producer_surfaces",
        "consumer_surfaces",
        "likely_false_positives",
    ):
        values = candidate.get(field)
        if isinstance(values, list) and len(_strings(cast(list[object], values))) != len(
            cast(list[object], values)
        ):
            errors.append(f"{prefix}.{field} must contain only non-empty strings")
    provenance = candidate.get("provenance")
    if isinstance(provenance, list) and any(
        not isinstance(item, dict) or not item for item in cast(list[object], provenance)
    ):
        errors.append(f"{prefix}.provenance must contain only non-empty objects")
    for field in ("producer_surfaces", "consumer_surfaces"):
        for value in _strings(candidate.get(field)):
            if safe_relative_path_value(value) is None:
                errors.append(f"{prefix}.{field} contains an unsafe path: {value}")
    signal = _mapping(candidate.get("detection_signal"))
    if signal is None:
        errors.append(f"{prefix}.detection_signal must be an object")
    else:
        for field in ("kind", "description"):
            if not _nonempty_string(signal.get(field)):
                errors.append(f"{prefix}.detection_signal.{field} must be a non-empty string")

    fixtures = _mapping(candidate.get("fixtures"))
    if fixtures is None:
        errors.append(f"{prefix}.fixtures must be an object")
    else:
        for fixture_kind in ("positive", "negative"):
            values = _strings(fixtures.get(fixture_kind))
            if not values:
                errors.append(f"{prefix}.fixtures.{fixture_kind} must be a non-empty array")
            for value in values:
                relative = safe_relative_path_value(value)
                if relative is None:
                    errors.append(
                        f"{prefix}.fixtures.{fixture_kind} contains an unsafe path: {value}"
                    )
                elif not (root / relative).exists():
                    errors.append(
                        f"{prefix}.fixtures.{fixture_kind} is missing from the repository: {value}"
                    )

    status = candidate.get("status")
    if status not in {*LIFECYCLE_STATUSES, *DISPOSITION_STATUSES}:
        errors.append(f"{prefix}.status is unsupported")
    transitions = objects(candidate.get("transitions"))
    errors.extend(_transition_errors(transitions, status, prefix))
    if status in DISPOSITION_STATUSES:
        disposition = _mapping(candidate.get("disposition"))
        if disposition is None:
            errors.append(f"{prefix}.disposition is required for terminal disposition")
        else:
            for field in ("kind", "rationale", "decided_by", "decided_at"):
                if not _nonempty_string(disposition.get(field)):
                    errors.append(f"{prefix}.disposition.{field} must be a non-empty string")
            if _parse_timestamp(disposition.get("decided_at")) is None:
                errors.append(f"{prefix}.disposition.decided_at must be timezone-aware ISO-8601")
            if disposition.get("kind") != status:
                errors.append(f"{prefix}.disposition.kind must match status")
    if status == "required-gate":
        promotion_receipt = safe_relative_path_value(candidate.get("promotion_receipt"))
        if promotion_receipt is None:
            errors.append(f"{prefix}.promotion_receipt is required at required-gate")
        else:
            errors.extend(
                f"{prefix}.{error}"
                for error in supported_receipt_errors(
                    root / promotion_receipt,
                    candidate=candidate,
                    candidate_id=str(candidate.get("id")),
                )
            )

    if not isinstance(candidate.get("observations"), list):
        errors.append(f"{prefix}.observations must be an array")
    observation_ids: set[str] = set()
    for index, observation in enumerate(objects(candidate.get("observations"))):
        observation_prefix = f"{prefix}.observations[{index}]"
        observation_id = observation.get("id")
        if not _stable_id(observation_id):
            errors.append(f"{observation_prefix}.id must be stable kebab-case")
        elif observation_id in observation_ids:
            errors.append(f"{observation_prefix}.id duplicates {observation_id}")
        else:
            observation_ids.add(str(observation_id))
        if observation.get("classification") not in OBSERVATION_CLASSIFICATIONS:
            errors.append(f"{observation_prefix}.classification is unsupported")
        if observation.get("result") not in OBSERVATION_RESULTS:
            errors.append(f"{observation_prefix}.result is unsupported")
        expected_result = {
            "true-positive": "detected",
            "false-positive": "detected",
            "true-negative": "not-detected",
            "false-negative": "not-detected",
            "unclassified": "blocked",
        }.get(str(observation.get("classification")))
        if expected_result is not None and observation.get("result") != expected_result:
            errors.append(
                f"{observation_prefix}.result must be {expected_result} for "
                f"{observation.get('classification')}"
            )
        if _parse_timestamp(observation.get("observed_at")) is None:
            errors.append(f"{observation_prefix}.observed_at must be timezone-aware ISO-8601")
        duration = observation.get("duration_ms")
        if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
            errors.append(f"{observation_prefix}.duration_ms must be a non-negative integer")
        evidence = _mapping(observation.get("evidence"))
        if evidence is None or not _nonempty_string(evidence.get("reference")):
            errors.append(f"{observation_prefix}.evidence.reference must be recorded")
    return errors


def _transition_errors(
    transitions: list[dict[str, Any]],
    final_status: object,
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    current: str | None = None
    previous_at: datetime | None = None
    for index, transition in enumerate(transitions):
        transition_prefix = f"{prefix}.transitions[{index}]"
        source = transition.get("from")
        target = transition.get("to")
        if index == 0:
            if source is not None or target != "repository-regression":
                errors.append(
                    f"{transition_prefix} must begin at repository-regression with from=null"
                )
        elif source != current:
            errors.append(f"{transition_prefix}.from must match the previous lifecycle state")
        if index > 0 and (
            not isinstance(source, str)
            or not isinstance(target, str)
            or target not in _ALLOWED_TRANSITIONS.get(source, set())
        ):
            errors.append(f"{transition_prefix} is not an allowed lifecycle transition")
        for field in ("at", "actor", "reason"):
            if not _nonempty_string(transition.get(field)):
                errors.append(f"{transition_prefix}.{field} must be a non-empty string")
        transition_at = _parse_timestamp(transition.get("at"))
        if transition_at is None:
            errors.append(f"{transition_prefix}.at must be timezone-aware ISO-8601")
        else:
            if previous_at is not None and transition_at < previous_at:
                errors.append(f"{transition_prefix}.at must not predate the previous transition")
            previous_at = transition_at
        if not _nonempty_list(transition.get("evidence")):
            errors.append(f"{transition_prefix}.evidence must be a non-empty array")
        current = str(target) if isinstance(target, str) else None
    if transitions and current != final_status:
        errors.append(f"{prefix}.status must match the last transition")
    return errors


def _validation_payload(*, root: Path, path: str, errors: list[str]) -> dict[str, Any]:
    return {
        "schema": "quality-runner-candidate-registry-validation-v0.1",
        "status": "rejected",
        "repo_root": str(root),
        "registry_path": path,
        "registry_schema": None,
        "regression_count": 0,
        "candidate_count": 0,
        "covered_regression_count": 0,
        "errors": errors,
        "registry": None,
        "provenance_hash": None,
    }


def _covered_regression_ids(candidates: list[dict[str, Any]]) -> set[str]:
    return {
        regression_id
        for candidate in candidates
        for regression_id in _strings(candidate.get("originating_regressions"))
    }


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str) and item]


def _mapping(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _nonempty_list(value: object) -> bool:
    return isinstance(value, list) and bool(cast(list[object], value))


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _stable_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and all(part.isalnum() and part == part.lower() for part in value.split("-"))
    )


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)
