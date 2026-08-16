from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import digest

FLEET_SCOPE_MANIFEST_SCHEMA = "quality-runner-fleet-scope/v1"
_ELIGIBILITY = {"eligible", "excluded"}
_DISTRIBUTION_VISIBILITY = {"public", "private", "local"}


def load_fleet_scope_manifest(path: Path, *, projects_root: Path) -> dict[str, Any]:
    """Load and normalize an exact, operator-owned fleet population manifest."""

    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"fleet scope manifest is not valid JSON: {source}") from error
    if not isinstance(payload, dict) or payload.get("schema") != FLEET_SCOPE_MANIFEST_SCHEMA:
        raise ValueError(
            f"fleet scope manifest must declare schema {FLEET_SCOPE_MANIFEST_SCHEMA}: {source}"
        )

    authority = _required_string(payload, "authority")
    generated_at = _required_string(payload, "generated_at")
    try:
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("fleet scope manifest generated_at must be ISO-8601") from error

    raw_repositories = payload.get("repositories")
    if not isinstance(raw_repositories, list) or not raw_repositories:
        raise ValueError("fleet scope manifest repositories must be a non-empty array")

    root = projects_root.expanduser().resolve()
    normalized: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, raw_repository in enumerate(raw_repositories):
        if not isinstance(raw_repository, dict):
            raise ValueError(f"fleet scope manifest repository {index} must be an object")
        raw_path = _required_string(raw_repository, "path")
        resolved = Path(raw_path).expanduser().resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(
                f"fleet scope manifest repository is outside projects_root: {resolved}"
            ) from error
        resolved_path = str(resolved)
        if resolved_path in seen_paths:
            raise ValueError(f"fleet scope manifest repository path is duplicated: {resolved}")
        seen_paths.add(resolved_path)

        eligibility = _required_string(raw_repository, "eligibility")
        if eligibility not in _ELIGIBILITY:
            raise ValueError(
                f"fleet scope manifest eligibility must be eligible or excluded: {resolved}"
            )
        reason = _required_string(raw_repository, "reason")
        if eligibility == "eligible" and not (resolved / ".git").exists():
            raise ValueError(f"eligible fleet repository is not a Git checkout: {resolved}")
        normalized_repository: dict[str, Any] = {
            "path": resolved_path,
            "eligibility": eligibility,
            "reason": reason,
        }
        distribution = _distribution_attestation(raw_repository.get("distribution"), index=index)
        if distribution is not None:
            normalized_repository["distribution"] = distribution
        normalized.append(normalized_repository)

    normalized.sort(key=lambda item: item["path"])
    eligible_paths = [item["path"] for item in normalized if item["eligibility"] == "eligible"]
    excluded = [item for item in normalized if item["eligibility"] == "excluded"]
    if not eligible_paths:
        raise ValueError("fleet scope manifest must include at least one eligible repository")

    provenance = {
        "schema": FLEET_SCOPE_MANIFEST_SCHEMA,
        "authority": authority,
        "generated_at": generated_at,
        "repositories": normalized,
    }
    return {
        **provenance,
        "source_path": str(source),
        "manifest_hash": digest(provenance),
        "eligible_paths": eligible_paths,
        "repository_attestations": {
            item["path"]: {"distribution": item["distribution"]}
            for item in normalized
            if item["eligibility"] == "eligible" and "distribution" in item
        },
        "eligible_path_hash": digest(eligible_paths),
        "eligible_repository_count": len(eligible_paths),
        "excluded_repository_count": len(excluded),
        "excluded_repositories": excluded,
    }


def population_coverage(
    *,
    repositories: list[dict[str, Any]],
    repository_paths: Sequence[Path] | None,
    fleet_policy: dict[str, Any],
    scope_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    if scope_manifest is not None:
        expected = int(scope_manifest["eligible_repository_count"])
        observed = len(repositories)
        if expected != observed:
            raise ValueError(
                "fleet scope manifest did not resolve to its expected unique repository count: "
                f"expected {expected}, observed {observed}"
            )
        return {
            "status": "complete",
            "source": "scope_manifest",
            "authority": scope_manifest["authority"],
            "generated_at": scope_manifest["generated_at"],
            "manifest_schema": scope_manifest["schema"],
            "manifest_hash": scope_manifest["manifest_hash"],
            "eligible_path_hash": scope_manifest["eligible_path_hash"],
            "expected_repository_count": expected,
            "observed_repository_count": observed,
            "excluded_repository_count": int(scope_manifest["excluded_repository_count"]),
        }
    if repository_paths is None:
        return {
            "status": "complete",
            "source": "automatic_discovery",
            "authority": fleet_policy.get("source", "default"),
            "expected_repository_count": len(repositories),
            "observed_repository_count": len(repositories),
            "excluded_repository_count": len(fleet_policy.get("exclude_paths", [])),
        }
    return {
        "status": "bounded",
        "source": "explicit_repository_paths",
        "expected_repository_count": len(repository_paths),
        "observed_repository_count": len(repositories),
        "excluded_repository_count": 0,
    }


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"fleet scope manifest field is missing: {key}")
    return value.strip()


def _distribution_attestation(value: Any, *, index: int) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"fleet scope manifest repository {index} distribution must be an object")
    visibility = _required_string(value, "visibility")
    if visibility not in _DISTRIBUTION_VISIBILITY:
        raise ValueError(
            "fleet scope manifest distribution visibility must be public, private, or local"
        )
    source = _required_string(value, "source")
    observed_at = _required_string(value, "observed_at")
    try:
        datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            "fleet scope manifest distribution observed_at must be ISO-8601"
        ) from error
    return {"visibility": visibility, "source": source, "observed_at": observed_at}
