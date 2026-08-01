from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from quality_runner.aggregate_coverage import LEAF_GATE_IDS
from quality_runner.readiness_evidence import (
    detected_versions as _detected_versions,
)
from quality_runner.readiness_evidence import (
    file_digest as _file_digest,
)
from quality_runner.readiness_evidence import (
    fresh_provenance_timestamp as _fresh_provenance_timestamp,
)
from quality_runner.readiness_evidence import (
    normalize_digest as _normalize_digest,
)
from quality_runner.readiness_evidence import (
    valid_digest as _valid_digest,
)
from quality_runner.readiness_gate_helpers import (
    blocked_gate as _blocked_gate,
)
from quality_runner.readiness_gate_helpers import (
    passed_gate as _passed_gate,
)


def provenance_gate(
    *,
    scan: dict[str, Any],
    current_git: dict[str, Any],
    evidence: dict[str, Any] | None,
    evidence_error: str | None,
) -> dict[str, Any]:
    head = current_git.get("head_sha")
    checks = scan.get("ci_checks")
    if not isinstance(head, str) or not head:
        return _blocked_gate("evidence_provenance", "current git HEAD is unavailable", "provenance")
    if not isinstance(checks, list) or not checks:
        return _blocked_gate(
            "evidence_provenance",
            "release readiness requires current CI evidence with provenance",
            "provenance",
        )
    for raw_check in cast(list[Any], checks):
        check = _dict(raw_check)
        if check is None:
            return _blocked_gate(
                "evidence_provenance", "CI evidence contains an invalid check", "provenance"
            )
        if check.get("head_sha") != head:
            return _blocked_gate(
                "evidence_provenance", "CI evidence does not match the current HEAD", "provenance"
            )
        branch = current_git.get("branch")
        if not isinstance(branch, str) or not branch or branch == "HEAD":
            return _blocked_gate(
                "evidence_provenance",
                "current git ref is unavailable for provenance matching",
                "provenance",
            )
        ref = check.get("ref")
        valid_refs = {branch, f"refs/heads/{branch}"}
        if not isinstance(ref, str) or not ref or ref not in valid_refs:
            return _blocked_gate(
                "evidence_provenance",
                "CI evidence is missing or mismatched ref information",
                "provenance",
            )
        if not check.get("workflow_run_id") or not check.get("captured_at"):
            return _blocked_gate(
                "evidence_provenance",
                "CI evidence is missing workflow identity or capture time",
                "provenance",
            )
        if check.get("conclusion") != "success":
            return _blocked_gate(
                "evidence_provenance",
                "CI evidence is not successful for the release target",
                "provenance",
            )
        if not _fresh_provenance_timestamp(check.get("captured_at")):
            return _blocked_gate(
                "evidence_provenance",
                "CI evidence is stale or has an invalid capture timestamp",
                "provenance",
            )
    if evidence_error is None and evidence is not None:
        target = _dict(evidence.get("target"))
        if target is None or target.get("head_sha") != head:
            return _blocked_gate(
                "evidence_provenance",
                "release evidence does not match the current HEAD",
                "provenance",
            )
        branch = current_git.get("branch")
        target_ref = target.get("ref")
        valid_refs: set[str] = (
            {branch, f"refs/heads/{branch}"}
            if isinstance(branch, str) and branch and branch != "HEAD"
            else set()
        )
        if (
            not isinstance(target_ref, str)
            or not target_ref
            or not valid_refs
            or target_ref not in valid_refs
        ):
            return _blocked_gate(
                "evidence_provenance",
                "release evidence target ref does not match the current branch",
                "provenance",
            )
        artifact = _dict(evidence.get("artifact"))
        artifact_digest = artifact.get("digest") if artifact is not None else None
        for raw_check in cast(list[Any], checks):
            check = _dict(raw_check)
            check_digest = check.get("artifact_digest") if check is not None else None
            if check_digest and _normalize_digest(check_digest) != _normalize_digest(
                artifact_digest
            ):
                return _blocked_gate(
                    "evidence_provenance",
                    "CI artifact digest does not match release evidence",
                    "provenance",
                )
    return _passed_gate("evidence_provenance", "CI and release evidence match the current HEAD")


def manifest_gate(
    *,
    repo_root: Path,
    current_git: dict[str, Any],
    evidence: dict[str, Any] | None,
    evidence_error: str | None,
    observed_digest: str | None = None,
) -> dict[str, Any]:
    versions = _detected_versions(repo_root)
    if not versions:
        return _blocked_gate(
            "release_manifest_coherence",
            "no supported package version metadata was found",
            "provenance",
        )
    if len(set(versions.values())) != 1:
        return _blocked_gate(
            "release_manifest_coherence",
            f"package version surfaces disagree: {versions}",
            "provenance",
        )
    if evidence_error is not None or evidence is None:
        return _blocked_gate(
            "release_manifest_coherence",
            evidence_error or "release evidence is missing",
            "evidence",
        )
    artifact = _dict(evidence.get("artifact"))
    if artifact is None:
        return _blocked_gate(
            "release_manifest_coherence", "artifact evidence is missing", "evidence"
        )
    expected_version = next(iter(versions.values()))
    if evidence.get("release_version") != expected_version:
        return _blocked_gate(
            "release_manifest_coherence",
            "reported release version does not match package metadata",
            "provenance",
        )
    if artifact.get("version") != expected_version:
        return _blocked_gate(
            "release_manifest_coherence",
            "artifact version does not match package metadata",
            "provenance",
        )
    if artifact.get("source_head") != current_git.get("head_sha"):
        return _blocked_gate(
            "release_manifest_coherence",
            "artifact source HEAD does not match the current HEAD",
            "provenance",
        )
    digest = artifact.get("digest")
    if not _valid_digest(digest):
        return _blocked_gate(
            "release_manifest_coherence", "artifact digest is missing or invalid", "evidence"
        )
    if observed_digest is not None and _normalize_digest(observed_digest) != _normalize_digest(
        digest
    ):
        return _blocked_gate(
            "release_manifest_coherence",
            "artifact digest does not match the observed release artifact",
            "provenance",
        )
    artifact_path = artifact.get("path")
    if isinstance(artifact_path, str) and artifact_path:
        path = Path(artifact_path).expanduser()
        if not path.is_absolute():
            path = repo_root / path
        path = Path(os.path.abspath(path))
        if path.is_symlink():
            return _blocked_gate(
                "release_manifest_coherence",
                "artifact path must not be a symlink",
                "provenance",
            )
        try:
            resolved_path = path.resolve(strict=False)
            resolved_path.relative_to(repo_root.resolve())
        except ValueError:
            return _blocked_gate(
                "release_manifest_coherence",
                "artifact path must be inside the target repository",
                "provenance",
            )
        if resolved_path != path:
            return _blocked_gate(
                "release_manifest_coherence",
                "artifact path must not traverse a symlinked path",
                "provenance",
            )
        if not resolved_path.is_file() or _file_digest(resolved_path) != _normalize_digest(digest):
            return _blocked_gate(
                "release_manifest_coherence",
                "artifact digest does not match the referenced local artifact",
                "provenance",
            )
    return _passed_gate(
        "release_manifest_coherence", "package metadata and artifact evidence agree"
    )


def acceptance_gate(
    *, evidence: dict[str, Any] | None, evidence_error: str | None
) -> dict[str, Any]:
    if evidence_error is not None or evidence is None:
        return _blocked_gate(
            "release_acceptance_evidence",
            evidence_error or "release evidence is missing",
            "review-required",
        )
    owner = _dict(evidence.get("owner"))
    acceptance = evidence.get("acceptance")
    if not isinstance(owner, dict) or not owner.get("name") or not owner.get("role"):
        return _blocked_gate(
            "release_acceptance_evidence", "owner acceptance is missing", "review-required"
        )
    if not isinstance(acceptance, list) or not any(
        (item := _dict(raw_item)) is not None and item.get("status") == "accepted"
        for raw_item in cast(list[Any], acceptance)
    ):
        return _blocked_gate(
            "release_acceptance_evidence",
            "no accepted owner decision was recorded",
            "review-required",
        )
    external_checks = evidence.get("external_checks")
    if isinstance(external_checks, list) and any(
        (item := _dict(raw_item)) is None or item.get("status") != "passed"
        for raw_item in cast(list[Any], external_checks)
    ):
        return _blocked_gate(
            "release_acceptance_evidence",
            "required external staging or cutover evidence is incomplete",
            "review-required",
        )
    return _passed_gate("release_acceptance_evidence", "owner acceptance evidence is present")


def migration_evidence_gate(
    *,
    evidence: dict[str, Any] | None,
    evidence_error: str | None,
    existing: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    existing_gate = existing.get("migration_safety")
    if existing_gate is not None:
        if existing_gate.get("status") == "passed":
            return _passed_gate("migration_safety", "migration safety command passed")
        if existing_gate.get("status") in {"failed", "blocked", "skipped"}:
            return _blocked_gate(
                "migration_safety",
                "migration safety command did not pass",
                "evidence",
            )
    if evidence_error is not None or evidence is None:
        return _blocked_gate(
            "migration_safety", evidence_error or "migration evidence is missing", "evidence"
        )
    migration = evidence.get("migration")
    migration = _dict(migration)
    if migration is None:
        return _blocked_gate("migration_safety", "migration evidence is missing", "evidence")
    required = ("forward", "rollback", "failure_injection", "reconciliation")
    if not all(_proof_passed(migration.get(key)) for key in required):
        return _blocked_gate(
            "migration_safety",
            "migration evidence must prove forward, rollback, failure injection, and reconciliation",
            "evidence",
        )
    return _passed_gate("migration_safety", "migration safety evidence is complete")


def _proof_passed(value: object) -> bool:
    if value == "passed":
        return True
    value_map = _dict(value)
    if value_map is None or value_map.get("status") != "passed":
        return False
    evidence = value_map.get("evidence")
    if not isinstance(evidence, list):
        return False
    evidence_items = cast(list[Any], evidence)
    return bool(evidence_items) and all(isinstance(item, str) and item for item in evidence_items)


def aggregate_gate(*, scan: dict[str, Any], capability_map: dict[str, Any]) -> dict[str, Any]:
    coverage = scan.get("aggregate_coverage")
    if not isinstance(coverage, list) or not coverage:
        return _passed_gate("aggregate_coverage", "no opaque aggregate commands were detected")
    coverage_rows = _dict_list(cast(object, coverage))
    opaque = [item for item in coverage_rows if item.get("opaque") is True]
    required_leaf_ids = {
        str(capability.get("id"))
        for key in ("available", "missing")
        for capability in _dict_list(capability_map.get(key))
        if capability.get("id") in LEAF_GATE_IDS
    }
    covered_leaf_ids: set[str] = set()
    for item in coverage_rows:
        if isinstance(item.get("covered_gate_ids"), list):
            covered_leaf_ids.update(
                gate_id for gate_id in item["covered_gate_ids"] if isinstance(gate_id, str)
            )
    uncovered = [
        item
        for item in coverage_rows
        if isinstance(item.get("covered_gate_ids"), list)
        and isinstance(item.get("uncovered_gate_ids"), list)
        and item["uncovered_gate_ids"]
    ]
    if required_leaf_ids - covered_leaf_ids:
        return _blocked_gate(
            "aggregate_coverage",
            "aggregate command coverage does not prove all required leaf gates",
            "coverage",
        )
    if opaque or uncovered:
        return _blocked_gate(
            "aggregate_coverage", "aggregate command coverage is incomplete or opaque", "coverage"
        )
    return _passed_gate("aggregate_coverage", "aggregate command coverage is proven")


def publication_gate(
    *,
    existing: dict[str, dict[str, Any]],
    capability_map: dict[str, Any],
    evidence: dict[str, Any] | None,
    evidence_error: str | None,
) -> dict[str, Any]:
    existing_gate = existing.get("publication_visibility_review")
    if existing_gate is not None and existing_gate.get("status") == "passed":
        return existing_gate
    security_gate = next(
        (
            capability
            for capability in _dict_list(capability_map.get("available"))
            if capability.get("id") == "security_publication_visibility_review"
        ),
        None,
    )
    if security_gate is not None and security_gate.get("status") == "review-complete":
        return _passed_gate("publication_visibility_review", "publication review was completed")
    publication = _dict(evidence.get("publication")) if evidence is not None else None
    required = ("authorization", "sanitization", "immutability", "media_access")
    if (
        evidence_error is None
        and publication is not None
        and all(_proof_passed(publication.get(key)) for key in required)
    ):
        return _passed_gate(
            "publication_visibility_review", "publication review evidence is complete"
        )
    return _blocked_gate(
        "publication_visibility_review",
        "publication and visibility review is required",
        "review-required",
    )


def read_only_gate(
    *, gate_verification: dict[str, Any], verification_context: dict[str, Any] | None
) -> dict[str, Any]:
    if (
        isinstance(verification_context, dict)
        and verification_context.get("worktree_mode") == "in-place"
    ):
        for gate in _dict_list(gate_verification.get("gates")):
            if gate.get("mutating_risk") in {"mutating", "unknown"}:
                return _blocked_gate(
                    "read_only_integrity",
                    "release profile requires disposable execution for mutating or unknown-risk gates",
                    "isolation",
                )
    for gate in _dict_list(gate_verification.get("gates")):
        if gate.get("failure_type") == "read-only-mutation":
            return _blocked_gate(
                "read_only_integrity", "a gate mutated the source worktree", "read-only-policy"
            )
    return _passed_gate("read_only_integrity", "no unauthorized read-only mutation was detected")


def _dict(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for raw_item in cast(list[Any], value) if (item := _dict(raw_item)) is not None]
