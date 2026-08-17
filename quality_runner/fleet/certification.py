from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from quality_runner.artifacts import write_json, write_text
from quality_runner.fleet.audit import (
    fleet_audit_payload,
    fleet_replay_payload,
    resolve_artifact_root,
)
from quality_runner.fleet.contracts import (
    FLEET_CERTIFICATION_SCHEMA,
    digest,
)
from quality_runner.fleet.maturity_projection import (
    MaturityProjectionError,
    repository_projection,
)
from quality_runner.fleet.scope_manifest import load_fleet_scope_manifest

CERTIFICATION_STATUSES = ("certified", "not_certified")
CHECK_STATES = ("passed", "failed", "blocked", "unavailable", "unknown", "not_applicable")
CHECK_NAMES = (
    "population_coverage",
    "audit_replay",
    "target_branch",
    "maturity_model",
    "dynamic_verification",
    "behavior_assurance",
)


def fleet_certification_payload(
    *,
    projects_root: Path,
    scope_manifest: Path,
    output_dir: Path | None = None,
    audit_id: str | None = None,
    parallelism: int = 8,
    timeout_seconds: int = 120,
    target_overrides: dict[str, str] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Run or aggregate one complete fleet certification snapshot.

    Fresh mode runs the existing read-only fleet audit with a bounded worker
    pool, then projects explicit certificate and proof-check counts. Reuse
    mode reads an immutable audit selected by ``audit_id`` and performs only
    the projection and replay checks.
    """

    if parallelism <= 0:
        raise ValueError("--parallelism must be positive")
    if timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be positive")

    root = projects_root.expanduser().resolve()
    manifest = load_fleet_scope_manifest(scope_manifest, projects_root=root)
    fresh = audit_id is None
    if fresh:
        audit = fleet_audit_payload(
            projects_root=root,
            output_dir=output_dir,
            dynamic=True,
            changed_only=False,
            timeout_seconds=timeout_seconds,
            target_overrides=target_overrides,
            as_of=as_of,
            scope_manifest=scope_path(scope_manifest),
            parallelism=parallelism,
        )
        artifact_root = Path(str(audit["artifact_root"])).expanduser().resolve()
    else:
        artifact_root = resolve_artifact_root(output_dir, audit_id)

    inventory = _read_object(artifact_root / "inventory.json")
    summary = _read_object(artifact_root / "summary.json")
    inventory_audit_id = _required_string(inventory, "audit_id")
    if audit_id is not None and inventory_audit_id != audit_id:
        raise ValueError(
            f"requested audit id {audit_id!r} does not match persisted audit {inventory_audit_id!r}"
        )
    if _required_string(inventory, "projects_root") != str(root):
        raise ValueError("persisted fleet audit projects root does not match --projects-root")

    coverage = _object(inventory.get("population_coverage"))
    manifest_hash = _required_string(manifest, "manifest_hash")
    coverage_hash = str(coverage.get("manifest_hash", ""))
    coverage_complete = (
        coverage.get("status") == "complete"
        and coverage.get("source") == "scope_manifest"
        and coverage_hash == manifest_hash
        and int(coverage.get("expected_repository_count", 0))
        == int(coverage.get("observed_repository_count", 0))
    )

    replay = _replay_payload(artifact_root)
    repositories = _objects(inventory.get("repositories"))
    findings_dir = artifact_root / "findings"
    repository_results: list[dict[str, Any]] = []
    for repository in repositories:
        repo_id = _required_string(repository, "repo_id")
        finding_path = findings_dir / f"{repo_id}.json"
        if not finding_path.is_file() or finding_path.is_symlink():
            repository_results.append(
                _missing_repository_result(
                    repository,
                    coverage_complete=coverage_complete,
                    replay=replay,
                )
            )
            continue
        try:
            finding = _read_object(finding_path)
            projection = repository_projection(repository, finding)
        except (MaturityProjectionError, ValueError, TypeError, json.JSONDecodeError) as error:
            repository_results.append(
                _invalid_repository_result(
                    repository,
                    reason=f"finding_projection_invalid:{type(error).__name__}",
                    coverage_complete=coverage_complete,
                    replay=replay,
                )
            )
            continue
        repository_results.append(
            _project_repository(
                projection,
                coverage_complete=coverage_complete,
                replay=replay,
            )
        )

    repository_results.sort(key=lambda item: str(item["repo_id"]))
    repository_count = len(repositories)
    certified_count = sum(
        item["certification_status"] == "certified" for item in repository_results
    )
    not_certified_count = repository_count - certified_count
    global_complete = (
        coverage_complete
        and replay["status"] == "passed"
        and len(repository_results) == repository_count
    )
    if global_complete and repository_count > 0 and certified_count == repository_count:
        overall_status = "certified"
    elif global_complete:
        overall_status = "review_required"
    else:
        overall_status = "blocked"

    proof_check_counts = {
        name: _count_check_states(repository_results, name) for name in CHECK_NAMES
    }
    blocking_reason_counts = dict(
        sorted(
            Counter(
                reason for item in repository_results for reason in item["blocking_reasons"]
            ).items()
        )
    )
    certification = {
        "status": overall_status,
        "complete": global_complete,
        "repository_count": repository_count,
        "certified_count": certified_count,
        "not_certified_count": not_certified_count,
        "proof_check_counts": proof_check_counts,
        "blocking_reason_counts": blocking_reason_counts,
    }
    payload: dict[str, Any] = {
        "schema": FLEET_CERTIFICATION_SCHEMA,
        "status": overall_status,
        "audit_id": inventory_audit_id,
        "as_of": _required_string(summary, "as_of"),
        "certification": certification,
        "source": {
            "mode": "fresh_audit" if fresh else "persisted_audit",
            "audit_id": inventory_audit_id,
            "audit_status": str(summary.get("status", "unknown")),
            "artifact_root": str(artifact_root),
            "projects_root": str(root),
            "scope_manifest": str(scope_path(scope_manifest)),
            "scope_manifest_hash": manifest_hash,
            "parallelism": parallelism,
            "timeout_seconds": timeout_seconds,
        },
        "replay": replay,
        "population_coverage": {
            "status": "complete" if coverage_complete else "blocked",
            "expected_repository_count": int(coverage.get("expected_repository_count", 0)),
            "observed_repository_count": int(coverage.get("observed_repository_count", 0)),
            "manifest_hash": coverage_hash or manifest_hash,
        },
        "methodology": {
            "certified_when": [
                "scope manifest coverage is complete",
                "audit replay passes deterministically",
                "target branch is ready",
                "repository maturity model is certified",
                "dynamic verification passes or reuses passing evidence",
                "behavior assurance is release-ready or explicitly not applicable",
            ],
            "unknown_evidence_is_not_certified": True,
            "source_checkouts_modified": False,
        },
        "repositories": repository_results,
        "implementation_allowed": False,
    }
    payload["provenance_hash"] = digest(payload)
    paths = {
        "certification_json": str(write_json(artifact_root / "certification.json", payload)),
        "certification_md": str(write_text(artifact_root / "certification.md", _markdown(payload))),
    }
    payload["artifact_root"] = str(artifact_root)
    payload["artifact_paths"] = paths
    return payload


def scope_path(path: Path) -> Path:
    """Resolve a scope path once at the command boundary."""

    return path.expanduser().resolve()


def _project_repository(
    projection: dict[str, Any], *, coverage_complete: bool, replay: dict[str, Any]
) -> dict[str, Any]:
    checks = {
        "population_coverage": _check(
            "passed" if coverage_complete else "blocked",
            None if coverage_complete else "scope_manifest_coverage_incomplete",
        ),
        "audit_replay": _check(
            "passed" if replay["status"] == "passed" else "blocked",
            None if replay["status"] == "passed" else "audit_replay_incomplete",
        ),
        "target_branch": _target_check(projection),
        "maturity_model": _maturity_check(projection),
        "dynamic_verification": _dynamic_check(projection),
        "behavior_assurance": _behavior_check(projection),
    }
    passed_for_certificate = all(
        checks[name]["status"] == "passed"
        or name == "behavior_assurance"
        and checks[name]["status"] == "not_applicable"
        for name in (
            "population_coverage",
            "audit_replay",
            "target_branch",
            "maturity_model",
            "dynamic_verification",
            "behavior_assurance",
        )
    )
    projection_certified = projection.get("maturity_status") == "certified"
    certified = passed_for_certificate and projection_certified
    reasons = _blocking_reasons(checks, projection)
    evidence_state = _evidence_state(checks)
    return {
        "repo_id": _required_string(projection, "repo_id"),
        "display_name": str(projection.get("display_name", projection["repo_id"])),
        "certification_status": "certified" if certified else "not_certified",
        "evidence_state": evidence_state,
        "proof_checks": checks,
        "blocking_reasons": reasons,
        "maturity_status": str(projection.get("maturity_status", "unknown")),
        "maturity_score": projection.get("maturity_score"),
    }


def _missing_repository_result(
    repository: dict[str, Any], *, coverage_complete: bool, replay: dict[str, Any]
) -> dict[str, Any]:
    repo_id = _required_string(repository, "repo_id")
    checks = {name: _check("blocked", "finding_artifact_missing") for name in CHECK_NAMES}
    checks["population_coverage"] = _check(
        "passed" if coverage_complete else "blocked",
        None if coverage_complete else "scope_manifest_coverage_incomplete",
    )
    checks["audit_replay"] = _check(
        "passed" if replay["status"] == "passed" else "blocked",
        None if replay["status"] == "passed" else "audit_replay_incomplete",
    )
    return {
        "repo_id": repo_id,
        "display_name": Path(str(repository.get("primary_path", repo_id))).name,
        "certification_status": "not_certified",
        "evidence_state": "blocked",
        "proof_checks": checks,
        "blocking_reasons": ["finding_artifact_missing"],
        "maturity_status": "unknown",
    }


def _invalid_repository_result(
    repository: dict[str, Any],
    *,
    reason: str,
    coverage_complete: bool,
    replay: dict[str, Any],
) -> dict[str, Any]:
    result = _missing_repository_result(
        repository,
        coverage_complete=coverage_complete,
        replay=replay,
    )
    result["blocking_reasons"] = [reason]
    return result


def _target_check(projection: Mapping[str, Any]) -> dict[str, str]:
    status = str(projection.get("target_branch_status", "unknown"))
    if status == "ready":
        return _check("passed")
    return _check("blocked", f"target_branch_{status}")


def _maturity_check(projection: Mapping[str, Any]) -> dict[str, str]:
    model = _object(projection.get("repository_maturity"))
    status = str(model.get("status", "unknown"))
    if status == "certified":
        return _check("passed")
    if status == "blocked":
        return _check("blocked", "maturity_model_blocked")
    if status == "unknown":
        return _check("unknown", "maturity_model_unknown")
    return _check("failed", f"maturity_model_{status}")


def _dynamic_check(projection: Mapping[str, Any]) -> dict[str, str]:
    status = str(projection.get("dynamic_status", "unknown"))
    if status in {"passed", "reused"}:
        return _check("passed")
    if status == "failed":
        return _check("failed", "dynamic_verification_failed")
    if status in {"blocked", "timeout"}:
        return _check("blocked", f"dynamic_verification_{status}")
    if status == "unavailable":
        return _check("unavailable", "dynamic_verification_unavailable")
    if status == "not_applicable":
        return _check("not_applicable", "dynamic_verification_not_applicable")
    return _check("unknown", "dynamic_verification_unknown")


def _behavior_check(projection: Mapping[str, Any]) -> dict[str, str]:
    behavior = _object(projection.get("behavior_assurance"))
    if behavior.get("applicability") == "not_applicable":
        return _check("not_applicable", "behavior_assurance_not_applicable")
    if behavior.get("release_ready") is True or behavior.get("result_status") == "passed":
        return _check("passed")
    if behavior.get("state") in {"missing_contract", "blocked"}:
        return _check("blocked", f"behavior_assurance_{behavior.get('state')}")
    if behavior.get("result_status") == "failed" or behavior.get("state") == "failed":
        return _check("failed", "behavior_assurance_failed")
    if behavior.get("result_status") == "not_applicable":
        return _check("not_applicable", "behavior_assurance_not_applicable")
    return _check("unknown", "behavior_assurance_unknown")


def _blocking_reasons(
    checks: Mapping[str, Mapping[str, str]], projection: Mapping[str, Any]
) -> list[str]:
    reasons = [
        str(check["reason"])
        for check in checks.values()
        if check.get("status") != "passed"
        and check.get("status") != "not_applicable"
        and check.get("reason")
    ]
    if projection.get("maturity_status") != "certified":
        for gap in cast(list[object], projection.get("dimension_gaps", []))[:8]:
            if isinstance(gap, dict):
                dimension = gap.get("dimension")
                if isinstance(dimension, str) and dimension:
                    reasons.append(f"dimension_gap:{dimension}")
    return list(dict.fromkeys(reasons))


def _evidence_state(checks: Mapping[str, Mapping[str, str]]) -> str:
    statuses = {str(check.get("status")) for check in checks.values()}
    if "unavailable" in statuses:
        return "unavailable"
    if "blocked" in statuses or "unknown" in statuses:
        return "blocked"
    if statuses and statuses <= {"not_applicable"}:
        return "not_applicable"
    return "complete"


def _check(status: str, reason: str | None = None) -> dict[str, str]:
    if status not in CHECK_STATES:
        raise ValueError(f"unsupported certification check state: {status}")
    result = {"status": status}
    if reason:
        result["reason"] = reason
    return result


def _count_check_states(results: list[dict[str, Any]], name: str) -> dict[str, int]:
    counts = Counter(
        str(_object(item.get("proof_checks")).get(name, {}).get("status", "unknown"))
        for item in results
    )
    return {state: int(counts.get(state, 0)) for state in CHECK_STATES}


def _replay_payload(artifact_root: Path) -> dict[str, Any]:
    try:
        replay = fleet_replay_payload(output_dir=artifact_root)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "status": "blocked",
            "deterministic": False,
            "reason": f"audit_replay_unavailable:{type(error).__name__}",
        }
    return {
        "status": str(replay.get("status", "blocked")),
        "deterministic": bool(replay.get("deterministic", False)),
        "manifest_valid": bool(replay.get("manifest_valid", False)),
        "source_summary_hash": replay.get("source_summary_hash"),
        "replayed_summary_hash": replay.get("replayed_summary_hash"),
    }


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return cast(dict[str, Any], payload)


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"fleet certification field is missing: {key}")
    return value


def _object(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in value if isinstance(item, dict)]


def _markdown(payload: Mapping[str, Any]) -> str:
    certification = _object(payload.get("certification"))
    lines = [
        "# Fleet certification",
        "",
        f"- Status: `{payload.get('status', 'blocked')}`",
        f"- Repositories: {int(certification.get('repository_count', 0))}",
        f"- Certified: {int(certification.get('certified_count', 0))}",
        f"- Not certified: {int(certification.get('not_certified_count', 0))}",
        "",
        "## Proof checks",
        "",
        "| Check | Passed | Failed | Blocked | Unavailable | Unknown | Not applicable |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    proof_counts = _object(certification.get("proof_check_counts"))
    for name in CHECK_NAMES:
        counts = _object(proof_counts.get(name))
        lines.append(
            f"| {name} | {int(counts.get('passed', 0))} | {int(counts.get('failed', 0))} | "
            f"{int(counts.get('blocked', 0))} | {int(counts.get('unavailable', 0))} | "
            f"{int(counts.get('unknown', 0))} | {int(counts.get('not_applicable', 0))} |"
        )
    lines.extend(
        [
            "",
            "Certification is granted only when every required proof check passes; "
            "unknown, blocked, unavailable, and failed evidence is never treated as a pass.",
            "",
        ]
    )
    return "\n".join(lines)
