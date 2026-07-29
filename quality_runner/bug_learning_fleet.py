from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import digest

CANDIDATE_FLEET_SCHEMA = "quality-runner-candidate-fleet-v0.1"
CLASSIFIED_OBSERVATIONS = {
    "true-positive",
    "true-negative",
    "false-positive",
    "false-negative",
}
OBSERVATION_CLASSIFICATIONS = {*CLASSIFIED_OBSERVATIONS, "unclassified"}
OBSERVATION_RESULTS = {"detected", "not-detected", "blocked"}
PROMOTION_MIN_INDEPENDENT_REPOSITORIES = 2
PROMOTION_MIN_CLASSIFIED_OBSERVATIONS = 5
PROMOTION_MIN_PRECISION = 0.95
PROMOTION_MAX_COST_MS = 30_000
PROMOTION_MAX_AGE_DAYS = 90
PROMOTION_CRITERIA_KEYS = {
    "independent_repository_occurrences",
    "classified_observation_history",
    "precision",
    "evaluation_cost",
    "freshness",
    "deterministic_fixtures",
    "clear_remediation",
    "candidate_contract_consistency",
}


def aggregate_groups(
    *,
    occurrences: list[dict[str, Any]],
    prior_observations: dict[str, list[dict[str, Any]]],
    as_of: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for occurrence in occurrences:
        candidate = occurrence["candidate"]
        grouped.setdefault(str(candidate["id"]), []).append(occurrence)
    return [
        _aggregate_group(
            candidate_id=candidate_id,
            occurrences=grouped[candidate_id],
            prior=prior_observations.get(candidate_id, []),
            as_of=as_of,
        )
        for candidate_id in sorted(grouped)
    ]


def prior_observations(path: Path) -> dict[str, list[dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("schema") != CANDIDATE_FLEET_SCHEMA:
        return {}
    return {
        str(candidate["id"]): _objects(candidate.get("observations"))
        for candidate in _objects(payload.get("candidates"))
        if isinstance(candidate.get("id"), str)
    }


def candidate_contract_hash(candidate: dict[str, Any] | None) -> str | None:
    if candidate is None:
        return None
    return digest(
        {
            "id": candidate.get("id"),
            "failure_pattern": candidate.get("failure_pattern"),
            "cause": candidate.get("cause"),
            "detection_signal": candidate.get("detection_signal"),
            "remediation": candidate.get("remediation"),
        }
    )


def provenance_hash_matches(payload: dict[str, Any]) -> bool:
    expected = payload.get("provenance_hash")
    without_hash = {key: value for key, value in payload.items() if key != "provenance_hash"}
    return isinstance(expected, str) and expected == digest(without_hash)


def _aggregate_group(
    *,
    candidate_id: str,
    occurrences: list[dict[str, Any]],
    prior: list[dict[str, Any]],
    as_of: str,
) -> dict[str, Any]:
    observations_by_key: dict[str, dict[str, Any]] = {}
    for observation in prior:
        observations_by_key[_observation_key(observation)] = observation
    for occurrence in occurrences:
        repo_id = str(occurrence["repo_id"])
        for observation in _objects(occurrence["candidate"].get("observations")):
            normalized = {
                **observation,
                "repo_id": repo_id,
                "registry_path": occurrence["registry_path"],
                "registry_provenance_hash": occurrence["registry_provenance_hash"],
            }
            observations_by_key[_observation_key(normalized)] = normalized
    observations = sorted(
        observations_by_key.values(),
        key=lambda item: (
            str(item.get("observed_at")),
            str(item.get("repo_id")),
            str(item.get("id")),
        ),
    )
    cutoff = _parse_timestamp(as_of)
    assert cutoff is not None
    fresh_after = cutoff - timedelta(days=PROMOTION_MAX_AGE_DAYS)
    fresh = [
        item
        for item in observations
        if (observed := _parse_timestamp(item.get("observed_at"))) is not None
        and fresh_after <= observed <= cutoff
    ]
    fresh_classified = [
        item for item in fresh if item.get("classification") in CLASSIFIED_OBSERVATIONS
    ]
    counts = {
        classification: sum(1 for item in fresh if item.get("classification") == classification)
        for classification in sorted(CLASSIFIED_OBSERVATIONS)
    }
    true_positives = counts["true-positive"]
    false_positives = counts["false-positive"]
    precision_denominator = true_positives + false_positives
    precision = round(true_positives / precision_denominator, 4) if precision_denominator else None
    occurrence_repositories = sorted(
        {str(item["repo_id"]) for item in fresh if item.get("classification") == "true-positive"}
    )
    costs = [int(item["duration_ms"]) for item in fresh if isinstance(item.get("duration_ms"), int)]
    candidate_records = [item["candidate"] for item in occurrences]
    contract_hashes = sorted(
        {
            contract_hash
            for item in candidate_records
            if (contract_hash := candidate_contract_hash(item)) is not None
        }
    )
    fixture_positive = sorted(
        {
            path
            for candidate in candidate_records
            for path in _strings(_object(candidate.get("fixtures")).get("positive"))
        }
    )
    fixture_negative = sorted(
        {
            path
            for candidate in candidate_records
            for path in _strings(_object(candidate.get("fixtures")).get("negative"))
        }
    )
    criteria = {
        "independent_repository_occurrences": _criterion(
            len(occurrence_repositories) >= PROMOTION_MIN_INDEPENDENT_REPOSITORIES,
            actual=len(occurrence_repositories),
            required=PROMOTION_MIN_INDEPENDENT_REPOSITORIES,
        ),
        "classified_observation_history": _criterion(
            len(fresh_classified) >= PROMOTION_MIN_CLASSIFIED_OBSERVATIONS,
            actual=len(fresh_classified),
            required=PROMOTION_MIN_CLASSIFIED_OBSERVATIONS,
        ),
        "precision": _criterion(
            precision is not None and precision >= PROMOTION_MIN_PRECISION,
            actual=precision,
            required=PROMOTION_MIN_PRECISION,
        ),
        "evaluation_cost": _criterion(
            bool(costs) and max(costs) <= PROMOTION_MAX_COST_MS,
            actual=max(costs) if costs else None,
            required=PROMOTION_MAX_COST_MS,
        ),
        "freshness": _criterion(
            bool(fresh_classified),
            actual=len(fresh_classified),
            required=f"classified evidence within {PROMOTION_MAX_AGE_DAYS} days",
        ),
        "deterministic_fixtures": _criterion(
            bool(fixture_positive) and bool(fixture_negative),
            actual={
                "positive": len(fixture_positive),
                "negative": len(fixture_negative),
            },
            required={"positive": 1, "negative": 1},
        ),
        "clear_remediation": _criterion(
            all(_nonempty_string(item.get("remediation")) for item in candidate_records),
            actual=len(
                [item for item in candidate_records if _nonempty_string(item.get("remediation"))]
            ),
            required=len(candidate_records),
        ),
        "candidate_contract_consistency": _criterion(
            len(contract_hashes) == 1,
            actual=len(contract_hashes),
            required=1,
        ),
    }
    statuses: dict[str, int] = {}
    for candidate in candidate_records:
        status = str(candidate.get("status"))
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "id": candidate_id,
        "repository_count": len({str(item["repo_id"]) for item in occurrences}),
        "registry_occurrence_count": len(occurrences),
        "status_counts": dict(sorted(statuses.items())),
        "independent_occurrence_repositories": occurrence_repositories,
        "observations": observations,
        "observation_counts": counts,
        "fresh_observation_count": len(fresh),
        "fresh_classified_observation_count": len(fresh_classified),
        "precision": precision,
        "false_positive_count": false_positives,
        "false_negative_count": counts["false-negative"],
        "max_duration_ms": max(costs) if costs else None,
        "latest_observed_at": max(
            (str(item.get("observed_at")) for item in observations),
            default=None,
        ),
        "fixtures": {"positive": fixture_positive, "negative": fixture_negative},
        "candidate_contract_hashes": contract_hashes,
        "promotion_criteria": criteria,
        "promotion_supported_by_evidence": all(value["passed"] for value in criteria.values()),
        "provenance_hash": digest(
            {
                "candidate_id": candidate_id,
                "occurrences": [
                    {
                        "repo_id": item["repo_id"],
                        "registry_provenance_hash": item["registry_provenance_hash"],
                    }
                    for item in occurrences
                ],
                "observations": observations,
            }
        ),
    }


def _observation_key(observation: dict[str, Any]) -> str:
    return digest(
        {
            "repo_id": observation.get("repo_id"),
            "id": observation.get("id"),
            "observed_at": observation.get("observed_at"),
            "evidence": observation.get("evidence"),
        }
    )


def _criterion(passed: bool, *, actual: object, required: object) -> dict[str, Any]:
    return {"passed": passed, "actual": actual, "required": required}


def _objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _object(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


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
