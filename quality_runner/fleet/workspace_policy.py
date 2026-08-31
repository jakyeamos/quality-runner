"""Read-only validation and projection for repository workspace roles.

The workspace policy is deliberately orthogonal to custody.  It identifies the
canonical workspaces that are protected by repository role; every other
workspace is a temporary lane and must be covered by an isolated-change lease.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from quality_runner.fleet.behavior_support import iso_timestamp

WORKSPACE_POLICY_SCHEMA = "workspace-policy/v1"
WORKSPACE_FLEET_MANIFEST_SCHEMA = "workspace-fleet-manifest/v1"
WORKSPACE_TARGET_SCHEMA = "quality-runner-workspace-target/v1"
DEFAULT_POLICY_RELATIVE_PATH = Path(".agents") / "workspace-policy.json"

ROLE_TARGETS: dict[str, int | None] = {
    "production_product": 2,
    "supporting_project": 1,
    "role_unresolved": None,
}

EXPECTED_CANONICAL_ROLES: dict[str, set[str]] = {
    "production_product": {"release", "integration"},
    "supporting_project": {"working"},
    "role_unresolved": set(),
}


def _error(message: str) -> ValueError:
    return ValueError(f"workspace policy: {message}")


def _object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(f"{context} must be an object")
    return cast(dict[str, Any], value)


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(f"{field} must be a non-empty string")
    return value.strip()


def _nonnegative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _error(f"{field} must be a non-negative integer")
    return value


def validate_workspace_policy(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one repository workspace policy."""

    payload = _object(dict(value), "policy")
    if payload.get("schema_version") != WORKSPACE_POLICY_SCHEMA:
        raise _error(f"schema_version must be {WORKSPACE_POLICY_SCHEMA}")
    role = payload.get("repository_role")
    if role not in ROLE_TARGETS:
        raise _error(
            "repository_role must be production_product, supporting_project, or role_unresolved"
        )
    role = cast(str, role)

    canonical_value = payload.get("canonical_workspaces")
    if not isinstance(canonical_value, list):
        raise _error("canonical_workspaces must be an array")
    canonical: list[dict[str, Any]] = []
    ids: set[str] = set()
    refs: set[str] = set()
    roles: set[str] = set()
    for index, item in enumerate(cast(list[object], canonical_value)):
        entry = _object(item, f"canonical_workspaces[{index}]")
        entry_id = _nonempty_string(entry.get("id"), f"canonical_workspaces[{index}].id")
        entry_role = _nonempty_string(entry.get("role"), f"canonical_workspaces[{index}].role")
        ref = _nonempty_string(entry.get("ref"), f"canonical_workspaces[{index}].ref")
        if entry_role not in {"release", "integration", "working"}:
            raise _error(f"canonical_workspaces[{index}].role is not supported")
        if entry_id in ids or ref in refs or entry_role in roles:
            raise _error("canonical workspace ids, refs, and roles must be unique")
        if entry.get("protected") is not True:
            raise _error(f"canonical_workspaces[{index}].protected must be true")
        path = entry.get("path")
        if path is not None:
            path = _nonempty_string(path, f"canonical_workspaces[{index}].path")
        ids.add(entry_id)
        refs.add(ref)
        roles.add(entry_role)
        canonical.append(
            {
                "id": entry_id,
                "role": entry_role,
                "ref": ref,
                "path": path,
                "protected": True,
            }
        )

    expected = EXPECTED_CANONICAL_ROLES[role]
    if role != "role_unresolved" and roles != expected:
        missing = sorted(expected - roles)
        extra = sorted(roles - expected)
        raise _error(
            f"canonical workspace roles do not match {role}; missing={missing}, extra={extra}"
        )

    retention_value = payload.get("retention_exceptions", [])
    if not isinstance(retention_value, list):
        raise _error("retention_exceptions must be an array")
    retention: list[dict[str, str]] = []
    retention_ids: set[str] = set()
    for index, item in enumerate(cast(list[object], retention_value)):
        entry = _object(item, f"retention_exceptions[{index}]")
        lane_id = _nonempty_string(entry.get("lane_id"), f"retention_exceptions[{index}].lane_id")
        reason = _nonempty_string(entry.get("reason"), f"retention_exceptions[{index}].reason")
        retained_by = _nonempty_string(
            entry.get("retained_by"), f"retention_exceptions[{index}].retained_by"
        )
        review_by = _nonempty_string(
            entry.get("review_by"), f"retention_exceptions[{index}].review_by"
        )
        if iso_timestamp(review_by) is None:
            raise _error(f"retention_exceptions[{index}].review_by must be ISO-8601")
        if lane_id in retention_ids:
            raise _error("retention exception lane_id values must be unique")
        retention_ids.add(lane_id)
        retention.append(
            {
                "lane_id": lane_id,
                "reason": reason,
                "retained_by": retained_by,
                "review_by": review_by,
            }
        )

    repository_id = payload.get("repository_id")
    if repository_id is not None:
        repository_id = _nonempty_string(repository_id, "repository_id")
    return {
        "schema_version": WORKSPACE_POLICY_SCHEMA,
        "repository_id": repository_id,
        "repository_role": role,
        "canonical_workspaces": canonical,
        "retention_exceptions": retention,
    }


def load_workspace_policy(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _error(f"could not read {path}: {error}") from error
    return validate_workspace_policy(_object(value, str(path)))


def default_workspace_policy_path(repository: Path) -> Path:
    return repository / DEFAULT_POLICY_RELATIVE_PATH


def _canonical(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _workspace_path(repository: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return _canonical(path if path.is_absolute() else repository / path)


def is_canonical_workspace(
    record: Mapping[str, Any], policy: Mapping[str, Any] | None, repository: Path
) -> bool:
    """Return whether a live worktree matches an explicitly protected workspace."""

    if policy is None:
        return _canonical(Path(str(record["path"]))) == _canonical(repository)
    if policy.get("repository_role") == "role_unresolved" and not policy.get(
        "canonical_workspaces"
    ):
        return _canonical(Path(str(record["path"]))) == _canonical(repository)
    branch = record.get("branch")
    path = _canonical(Path(str(record["path"])))
    for workspace in policy.get("canonical_workspaces", []):
        if branch == workspace.get("ref"):
            return True
        expected_path = _workspace_path(repository, workspace.get("path"))
        if expected_path is not None and path == expected_path:
            return True
    return False


def workspace_policy_projection(
    policy: Mapping[str, Any] | None,
    *,
    repository: Path,
    observed_workspaces: Iterable[Mapping[str, Any]],
    active_temporary_lanes: int = 0,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    """Project policy, live workspace classes, and target drift."""

    records = list(observed_workspaces)
    if policy is None:
        return {
            "schema_version": WORKSPACE_POLICY_SCHEMA,
            "repository_role": "role_unresolved",
            "status": "role_unresolved",
            "disposition": "policy_missing",
            "baseline_target": None,
            "canonical_target": None,
            "canonical_observed": 0,
            "temporary_observed": len(records),
            "active_temporary_lanes": active_temporary_lanes,
            "retained_lane_count": 0,
            "managed_target_total": None,
            "canonical_workspaces": [],
            "protected_refs": [],
            "lease_required_for": "temporary",
            "canonical_protection": "unresolved",
            "policy_path": str(policy_path) if policy_path else None,
            "drift": ["repository-role-unresolved"],
        }

    normalized = validate_workspace_policy(policy)
    role = normalized["repository_role"]
    target = ROLE_TARGETS[role]
    canonical = normalized["canonical_workspaces"]
    observed_roles: set[str] = set()
    for record in records:
        branch = record.get("branch")
        path = _canonical(Path(str(record["path"])))
        for workspace in canonical:
            expected_path = _workspace_path(repository, workspace.get("path"))
            if branch == workspace["ref"] or (expected_path is not None and path == expected_path):
                observed_roles.add(workspace["role"])
                break
    expected_roles = EXPECTED_CANONICAL_ROLES[role]
    drift = [f"missing-canonical:{item}" for item in sorted(expected_roles - observed_roles)]
    canonical_observed = len(observed_roles)
    temporary_observed = sum(
        1 for record in records if not is_canonical_workspace(record, normalized, repository)
    )
    retained = len(normalized["retention_exceptions"])
    if role == "role_unresolved":
        status = "role_unresolved"
        disposition = "role_unresolved"
    elif drift:
        status = "canonical_drift"
        disposition = "canonical_workspace_missing"
    else:
        status = "observed"
        disposition = "policy_observed"
    managed_target_total = (
        target + active_temporary_lanes + retained if target is not None else None
    )
    return {
        "schema_version": WORKSPACE_POLICY_SCHEMA,
        "repository_id": normalized.get("repository_id"),
        "repository_role": role,
        "status": status,
        "disposition": disposition,
        "baseline_target": target,
        "canonical_target": target,
        "canonical_observed": canonical_observed,
        "temporary_observed": temporary_observed,
        "active_temporary_lanes": active_temporary_lanes,
        "retained_lane_count": retained,
        "managed_target_total": managed_target_total,
        "canonical_workspaces": canonical,
        "protected_refs": [item["ref"] for item in canonical if item["protected"]],
        "lease_required_for": "temporary",
        "canonical_protection": "enforced",
        "policy_path": str(policy_path) if policy_path else None,
        "drift": drift,
    }


def invalid_workspace_policy_projection(
    error: str,
    *,
    policy_path: Path,
    active_temporary_lanes: int = 0,
) -> dict[str, Any]:
    """Project an invalid policy without allowing it to authorize custody."""

    return {
        "schema_version": WORKSPACE_POLICY_SCHEMA,
        "repository_role": "role_unresolved",
        "status": "invalid",
        "disposition": "policy_invalid",
        "baseline_target": None,
        "canonical_target": None,
        "canonical_observed": 0,
        "temporary_observed": 0,
        "active_temporary_lanes": active_temporary_lanes,
        "retained_lane_count": 0,
        "managed_target_total": None,
        "canonical_workspaces": [],
        "protected_refs": [],
        "lease_required_for": "temporary",
        "canonical_protection": "unresolved",
        "policy_path": str(policy_path),
        "drift": [f"policy-invalid:{error}"],
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _error(f"could not read fleet manifest {path}: {error}") from error
    manifest = _object(value, str(path))
    if manifest.get("schema_version") != WORKSPACE_FLEET_MANIFEST_SCHEMA:
        raise _error(f"fleet manifest schema_version must be {WORKSPACE_FLEET_MANIFEST_SCHEMA}")
    repositories = manifest.get("repositories")
    if not isinstance(repositories, list):
        raise _error("fleet manifest repositories must be an array")
    return manifest


def fleet_workspace_target_payload(
    manifest_path: Path, *, as_of: str | None = None
) -> dict[str, Any]:
    """Calculate the fleet baseline target without mutating repositories."""

    manifest = _load_manifest(manifest_path)
    observed_at = iso_timestamp(as_of) if as_of else datetime.now(UTC)
    if observed_at is None:
        raise _error("as_of must be an ISO-8601 timestamp")
    rows: list[dict[str, Any]] = []
    production_count = 0
    supporting_count = 0
    unresolved_count = 0
    active_temporary_lanes = 0
    retained_lane_count = 0
    for index, item in enumerate(manifest["repositories"]):
        entry = _object(item, f"repositories[{index}]")
        policy_value = entry.get("policy", entry)
        policy = validate_workspace_policy(_object(policy_value, f"repositories[{index}].policy"))
        role = policy["repository_role"]
        if role == "production_product":
            production_count += 1
        elif role == "supporting_project":
            supporting_count += 1
        else:
            unresolved_count += 1
        temporary = _nonnegative_integer(
            entry.get("active_temporary_lanes", 0),
            f"repositories[{index}].active_temporary_lanes",
        )
        retained = len(policy["retention_exceptions"])
        active_temporary_lanes += temporary
        retained_lane_count += retained
        rows.append(
            {
                "repository_id": policy.get("repository_id") or entry.get("repository_id"),
                "repository_role": role,
                "baseline_target": ROLE_TARGETS[role],
                "active_temporary_lanes": temporary,
                "retained_lane_count": retained,
                "canonical_workspaces": policy["canonical_workspaces"],
                "lease_required_for": "temporary",
            }
        )
    baseline_target = 2 * production_count + supporting_count
    managed_target_total = (
        baseline_target + active_temporary_lanes + retained_lane_count
        if unresolved_count == 0
        else None
    )
    return {
        "schema_version": WORKSPACE_TARGET_SCHEMA,
        "generated_at": observed_at.isoformat(),
        "manifest": str(manifest_path.expanduser().resolve(strict=False)),
        "repository_count": len(rows),
        "production_count": production_count,
        "supporting_count": supporting_count,
        "role_unresolved_count": unresolved_count,
        "baseline_target": baseline_target if unresolved_count == 0 else None,
        "active_temporary_lanes": active_temporary_lanes,
        "retained_lane_count": retained_lane_count,
        "managed_target_total": managed_target_total,
        "status": "role_unresolved" if unresolved_count else "observed",
        "disposition": "role_unresolved" if unresolved_count else "formula_observed",
        "lease_policy": {
            "canonical_workspaces": "protected_by_role",
            "temporary_workspaces": "lease_required",
            "retained_workspaces": "explicit_exception_with_review_by",
        },
        "repositories": rows,
        "read_only": True,
        "implementation_allowed": False,
        "mutation_risk": "read-only",
    }
