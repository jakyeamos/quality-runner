from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.artifacts import write_json
from quality_runner.bug_learning_fleet import (
    CANDIDATE_FLEET_SCHEMA,
    PROMOTION_CRITERIA_KEYS,
    aggregate_groups,
    candidate_contract_hash,
    prior_observations,
    provenance_hash_matches,
)
from quality_runner.bug_learning_promotion import (
    PROMOTION_DECISION_SCHEMA as PROMOTION_DECISION_SCHEMA,
)
from quality_runner.bug_learning_promotion import (
    PROMOTION_RECEIPT_SCHEMA,
    candidate_by_id,
    promotion_decision_errors,
    read_object,
    supported_receipt_errors,
)
from quality_runner.bug_learning_registry import (
    CANDIDATE_REGISTRY_FILE,
    objects,
    safe_relative_path_value,
)
from quality_runner.bug_learning_registry import (
    validate_candidate_registry as validate_candidate_registry,
)
from quality_runner.fleet.contracts import digest, parse_as_of
from quality_runner.fleet.discovery import discover_repositories


def aggregate_candidate_fleet(
    *,
    projects_root: Path,
    output_path: Path,
    as_of: str | None = None,
) -> dict[str, Any]:
    root = projects_root.expanduser().resolve()
    observed_at = parse_as_of(as_of)
    repositories = discover_repositories(root)
    invalid_registries: list[dict[str, Any]] = []
    occurrences: list[dict[str, Any]] = []
    for repository in repositories:
        repo_path = Path(str(repository["primary_path"]))
        registry_path = repo_path / CANDIDATE_REGISTRY_FILE
        if not registry_path.is_file():
            continue
        validation = validate_candidate_registry(repo_path)
        if validation["status"] != "passed":
            invalid_registries.append(
                {
                    "repo_id": repository["repo_id"],
                    "registry_path": str(registry_path),
                    "errors": validation["errors"],
                }
            )
            continue
        registry = validation["registry"]
        assert isinstance(registry, dict)
        for candidate in objects(registry.get("candidates")):
            occurrences.append(
                {
                    "repo_id": repository["repo_id"],
                    "repository": registry.get("repository"),
                    "registry_path": str(registry_path),
                    "registry_provenance_hash": validation["provenance_hash"],
                    "candidate": candidate,
                }
            )

    destination = output_path.expanduser().resolve()
    groups = aggregate_groups(
        occurrences=occurrences,
        prior_observations=prior_observations(destination),
        as_of=observed_at,
    )
    payload = {
        "schema": CANDIDATE_FLEET_SCHEMA,
        "status": "blocked" if invalid_registries else "completed",
        "as_of": observed_at,
        "projects_root": str(root),
        "repository_count": len(repositories),
        "registry_count": len({occurrence["registry_path"] for occurrence in occurrences}),
        "candidate_occurrence_count": len(occurrences),
        "invalid_registries": invalid_registries,
        "candidates": groups,
    }
    payload["provenance_hash"] = digest(payload)
    write_json(destination, payload)
    return {
        **payload,
        "artifact_path": str(destination),
        "implementation_allowed": False,
    }


def check_candidate_promotion(
    *,
    repo_root: Path,
    candidate_id: str,
    fleet_evidence_path: Path,
    decision_path: Path,
    registry_path: str = CANDIDATE_REGISTRY_FILE,
    output_path: Path | None = None,
) -> dict[str, Any]:
    validation = validate_candidate_registry(repo_root, registry_path=registry_path)
    errors = list(validation["errors"])
    registry = validation.get("registry")
    candidate = candidate_by_id(registry, candidate_id)
    if candidate is None:
        errors.append(f"candidate is missing from registry: {candidate_id}")

    fleet = read_object(fleet_evidence_path, errors, label="fleet evidence")
    group = candidate_by_id(fleet, candidate_id)
    if fleet is not None and fleet.get("schema") != CANDIDATE_FLEET_SCHEMA:
        errors.append("fleet evidence schema is unsupported")
    if fleet is not None and fleet.get("status") != "completed":
        errors.append("fleet evidence is incomplete or blocked")
    if fleet is not None and not provenance_hash_matches(fleet):
        errors.append("fleet evidence provenance hash does not match its content")
    if group is None:
        errors.append(f"candidate is missing from fleet evidence: {candidate_id}")

    decision = read_object(decision_path, errors, label="promotion decision")
    if decision is not None:
        errors.extend(promotion_decision_errors(decision, candidate_id, fleet))

    raw_criteria = group.get("promotion_criteria") if isinstance(group, dict) else None
    criteria: dict[str, Any] = raw_criteria if isinstance(raw_criteria, dict) else {}
    if set(criteria) != PROMOTION_CRITERIA_KEYS:
        errors.append("promotion criteria are missing, extra, or unsupported")
    failed_criteria = sorted(
        key
        for key, value in criteria.items()
        if not isinstance(value, dict) or value.get("passed") is not True
    )
    if failed_criteria:
        errors.append(f"promotion criteria failed: {', '.join(failed_criteria)}")
    if candidate is not None and candidate.get("status") not in {
        "fleet-observation",
        "required-gate",
    }:
        errors.append("candidate lifecycle has not reached fleet-observation")

    supported = not errors
    receipt = {
        "schema": PROMOTION_RECEIPT_SCHEMA,
        "status": "supported" if supported else "blocked",
        "candidate_id": candidate_id,
        "decision": decision.get("decision") if isinstance(decision, dict) else None,
        "decided_by": decision.get("decided_by") if isinstance(decision, dict) else None,
        "decided_at": decision.get("decided_at") if isinstance(decision, dict) else None,
        "decision_reason": decision.get("reason") if isinstance(decision, dict) else None,
        "registry_provenance_hash": validation.get("provenance_hash"),
        "candidate_contract_hash": candidate_contract_hash(candidate),
        "fleet_provenance_hash": fleet.get("provenance_hash") if isinstance(fleet, dict) else None,
        "promotion_criteria": criteria,
        "errors": errors,
    }
    receipt["provenance_hash"] = digest(receipt)
    if output_path is None:
        return receipt
    destination = output_path.expanduser().resolve()
    write_json(destination, receipt)
    return {**receipt, "artifact_path": str(destination)}


def required_promotion_blocker(repo_root: Path, invariant: dict[str, Any]) -> str | None:
    if invariant.get("enforcement") != "required":
        return None
    candidate_id = invariant.get("candidate_id")
    if not isinstance(candidate_id, str):
        return None
    relative = invariant.get("promotion_receipt")
    if not isinstance(relative, str):
        return "candidate-linked required invariant is missing promotion_receipt"
    path_value = safe_relative_path_value(relative)
    if path_value is None:
        return "candidate-linked required invariant promotion_receipt path is unsafe"
    validation = validate_candidate_registry(repo_root)
    if validation["status"] != "passed":
        first_error = next(iter(validation["errors"]), "unknown registry error")
        return (
            f"candidate-linked required invariant has an invalid candidate registry: {first_error}"
        )
    candidate = candidate_by_id(validation.get("registry"), candidate_id)
    if candidate is None:
        return "candidate-linked required invariant candidate is missing from registry"
    if candidate.get("status") != "required-gate":
        return "candidate-linked required invariant candidate is not at required-gate"
    if candidate.get("promotion_receipt") != relative:
        return "invariant and candidate promotion_receipt paths do not match"
    receipt_errors = supported_receipt_errors(
        repo_root / path_value,
        candidate=candidate,
        candidate_id=candidate_id,
    )
    if receipt_errors:
        return receipt_errors[0]
    return None
