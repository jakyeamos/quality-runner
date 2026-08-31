from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from quality_runner import __version__
from quality_runner.artifacts import write_json
from quality_runner.onboarding_quality import quality_violations

ONBOARDING_CHECK_SCHEMA = "quality-runner-onboarding-check/v1"
ONBOARDING_EVIDENCE_SCHEMA = "quality-runner-onboarding-evidence/v1"
EXECUTABLE_QUALITY_SURFACE = "executable-quality-evidence"
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024


def onboarding_check_payload(
    *,
    repo_root: Path,
    matrix_path: Path,
    evidence_path: Path | None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Compute fail-closed onboarding readiness without changing the target repository."""

    root = repo_root.expanduser().resolve()
    resolved_matrix = matrix_path.expanduser().resolve()
    resolved_evidence = evidence_path.expanduser().resolve() if evidence_path is not None else None

    matrix, matrix_read_violations = _read_object(resolved_matrix, label="matrix")
    matrix_digest = _sha256_path(resolved_matrix)
    branch, head_sha, dirty_paths = _git_provenance(root)
    evidence, evidence_read_violations = _read_object(
        resolved_evidence, label="evidence", missing_allowed=False
    )

    checks = [
        _matrix_contract_check(matrix, matrix_read_violations),
        _source_provenance_check(branch, head_sha, dirty_paths),
        _evidence_contract_check(evidence, evidence_read_violations),
        _evidence_matrix_check(evidence, matrix_digest),
        _evidence_provenance_check(
            evidence,
            repository_id=root.name,
            branch=branch,
            head_sha=head_sha,
        ),
    ]
    surfaces = _surface_checks(
        root=root,
        matrix=matrix,
        evidence=evidence,
        branch=branch,
        head_sha=head_sha,
    )
    blocking_checks = [check for check in checks if check["status"] != "passed"]
    blocking_surfaces = [surface for surface in surfaces if surface["status"] != "passed"]
    passed = not blocking_checks and not blocking_surfaces

    return {
        "schema": ONBOARDING_CHECK_SCHEMA,
        "status": "passed" if passed else "blocked",
        "readiness": "ready" if passed else "not_ready",
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "producer": {"id": "quality-runner", "version": __version__},
        "repository": {
            "id": root.name,
            "path": str(root),
            "branch": branch,
            "head_sha": head_sha,
            "dirty_path_count": len(dirty_paths),
        },
        "matrix": {
            "path": str(resolved_matrix),
            "sha256": matrix_digest,
        },
        "evidence": {
            "path": str(resolved_evidence) if resolved_evidence is not None else None,
            "sha256": _sha256_path(resolved_evidence),
        },
        "checks": checks,
        "surfaces": surfaces,
        "blocking_check_ids": [str(check["id"]) for check in blocking_checks],
        "blocking_surface_ids": [str(surface["id"]) for surface in blocking_surfaces],
    }


def write_onboarding_report(payload: dict[str, Any], output_path: Path) -> Path:
    """Persist an explicitly requested machine receipt using the shared safe writer."""

    destination = output_path.expanduser().resolve()
    payload["output_path"] = str(destination)
    return write_json(destination, payload)


def _matrix_contract_check(
    matrix: dict[str, Any], read_violations: list[dict[str, Any]]
) -> dict[str, Any]:
    violations = list(read_violations)
    if matrix.get("schema_version") != "change-surface-matrix/v1":
        violations.append({"rule": "matrix-schema", "path": "schema_version"})
    baseline = _object(matrix.get("baseline"))
    required = _string_list(baseline.get("required_on_add"))
    conditional = _conditional_surface_ids(baseline)
    if not required:
        violations.append({"rule": "missing-required-surfaces", "path": "baseline.required_on_add"})
    surfaces = matrix.get("surfaces")
    surface_ids = {
        str(surface.get("id"))
        for surface in _object_list(surfaces)
        if isinstance(surface.get("id"), str)
    }
    if not surface_ids:
        violations.append({"rule": "missing-surface-registry", "path": "surfaces"})
    for surface_id in [*required, *conditional]:
        if surface_id not in surface_ids:
            violations.append({"rule": "unregistered-baseline-surface", "path": surface_id})
    validator = _object(matrix.get("onboarding_validator"))
    if validator.get("command") is None:
        violations.append({"rule": "missing-validator-command", "path": "onboarding_validator"})
    if validator.get("evidence_schema") != ONBOARDING_EVIDENCE_SCHEMA:
        violations.append(
            {"rule": "evidence-schema", "path": "onboarding_validator.evidence_schema"}
        )
    if validator.get("receipt_schema") != ONBOARDING_CHECK_SCHEMA:
        violations.append({"rule": "receipt-schema", "path": "onboarding_validator.receipt_schema"})
    producers = _object(validator.get("surface_producers"))
    for surface_id in [*required, *conditional]:
        if not _string_list(producers.get(surface_id)):
            violations.append({"rule": "missing-approved-producer", "path": surface_id})
    executable_quality = _object(validator.get("executable_quality"))
    if EXECUTABLE_QUALITY_SURFACE in required:
        if not _string_list(executable_quality.get("required_gates")):
            violations.append(
                {
                    "rule": "missing-required-quality-gates",
                    "path": "onboarding_validator.executable_quality.required_gates",
                }
            )
        if not _string_list(executable_quality.get("required_negative_controls")):
            violations.append(
                {
                    "rule": "missing-required-negative-controls",
                    "path": "onboarding_validator.executable_quality.required_negative_controls",
                }
            )
    return _check("matrix_contract", violations)


def _source_provenance_check(
    branch: str | None,
    head_sha: str | None,
    dirty_paths: list[str],
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    if branch is None:
        violations.append({"rule": "branch-unavailable", "path": "repository.branch"})
    if head_sha is None:
        violations.append({"rule": "head-unavailable", "path": "repository.head_sha"})
    if dirty_paths:
        violations.append(
            {
                "rule": "dirty-repository",
                "path": "repository",
                "count": len(dirty_paths),
                "paths": dirty_paths[:20],
            }
        )
    return _check("source_provenance", violations)


def _evidence_contract_check(
    evidence: dict[str, Any], read_violations: list[dict[str, Any]]
) -> dict[str, Any]:
    violations = list(read_violations)
    if evidence.get("schema") != ONBOARDING_EVIDENCE_SCHEMA:
        violations.append({"rule": "evidence-schema", "path": "schema"})
    if not isinstance(evidence.get("repository"), dict):
        violations.append({"rule": "missing-repository", "path": "repository"})
    if not isinstance(evidence.get("surfaces"), list):
        violations.append({"rule": "missing-surfaces", "path": "surfaces"})
    if not _is_sha256(evidence.get("matrix_sha256")):
        violations.append({"rule": "invalid-matrix-digest", "path": "matrix_sha256"})
    return _check("evidence_contract", violations)


def _evidence_matrix_check(evidence: dict[str, Any], matrix_digest: str | None) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    evidence_digest = evidence.get("matrix_sha256")
    if matrix_digest is None:
        violations.append({"rule": "matrix-digest-unavailable", "path": "matrix"})
    elif evidence_digest != matrix_digest:
        violations.append(
            {
                "rule": "matrix-digest-mismatch",
                "path": "matrix_sha256",
                "expected": matrix_digest,
                "observed": evidence_digest,
            }
        )
    return _check("evidence_matrix", violations)


def _evidence_provenance_check(
    evidence: dict[str, Any],
    *,
    repository_id: str,
    branch: str | None,
    head_sha: str | None,
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    target = _object(evidence.get("repository"))
    if target.get("id") != repository_id:
        violations.append(
            {
                "rule": "repository-id-mismatch",
                "path": "repository.id",
                "expected": repository_id,
                "observed": target.get("id"),
            }
        )
    violations.extend(_exact_ref_violations(target, branch=branch, head_sha=head_sha))
    return _check("evidence_provenance", violations)


def _surface_checks(
    *,
    root: Path,
    matrix: dict[str, Any],
    evidence: dict[str, Any],
    branch: str | None,
    head_sha: str | None,
) -> list[dict[str, Any]]:
    baseline = _object(matrix.get("baseline"))
    required_ids = _string_list(baseline.get("required_on_add"))
    conditional_ids = _conditional_surface_ids(baseline)
    validator = _object(matrix.get("onboarding_validator"))
    producers = _object(validator.get("surface_producers"))
    entries = _surface_entries(evidence.get("surfaces"))
    checks: list[dict[str, Any]] = []
    for surface_id in [*required_ids, *conditional_ids]:
        expected_kind = "required" if surface_id in required_ids else "conditional"
        matching = entries.get(surface_id, [])
        violations: list[dict[str, Any]] = []
        entry = matching[0] if matching else {}
        if not matching:
            violations.append({"rule": "missing-surface-evidence", "path": surface_id})
        if len(matching) > 1:
            violations.append({"rule": "duplicate-surface-evidence", "path": surface_id})
        if entry:
            status = entry.get("status")
            if expected_kind == "required" and status != "passed":
                violations.append(
                    {"rule": "required-surface-not-passed", "path": surface_id, "status": status}
                )
            elif expected_kind == "conditional" and status not in {"passed", "not_applicable"}:
                violations.append(
                    {
                        "rule": "conditional-surface-unresolved",
                        "path": surface_id,
                        "status": status,
                    }
                )
            if status == "not_applicable" and not _nonempty_string(entry.get("reason")):
                violations.append({"rule": "missing-not-applicable-reason", "path": surface_id})
            producer = _object(entry.get("producer"))
            allowed = _string_list(producers.get(surface_id))
            if producer.get("id") not in allowed:
                violations.append(
                    {
                        "rule": "unapproved-producer",
                        "path": surface_id,
                        "allowed": allowed,
                        "observed": producer.get("id"),
                    }
                )
            if not _nonempty_string(producer.get("version")):
                violations.append({"rule": "missing-producer-version", "path": surface_id})
            if not _nonempty_string(entry.get("observed_at")):
                violations.append({"rule": "missing-observed-at", "path": surface_id})
            if not _string_list(entry.get("evidence")):
                violations.append({"rule": "missing-evidence", "path": surface_id})
            violations.extend(
                _exact_ref_violations(
                    _object(entry.get("target")), branch=branch, head_sha=head_sha
                )
            )
            if surface_id == EXECUTABLE_QUALITY_SURFACE:
                violations.extend(
                    quality_violations(
                        root=root,
                        details=_object(entry.get("details")),
                        policy=_object(validator.get("executable_quality")),
                        branch=branch,
                        head_sha=head_sha,
                    )
                )
        checks.append(
            {
                "id": surface_id,
                "kind": expected_kind,
                "status": "passed" if not violations else "blocked",
                "evidence_status": entry.get("status") if entry else "missing",
                "violations": violations,
            }
        )
    return checks


def _surface_entries(value: object) -> dict[str, list[dict[str, Any]]]:
    entries: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(value, list):
        return entries
    for raw in cast(list[object], value):
        if not isinstance(raw, dict):
            continue
        entry = cast(dict[str, Any], raw)
        if not isinstance(entry.get("surface_id"), str):
            continue
        entries.setdefault(str(entry["surface_id"]), []).append(entry)
    return entries


def _exact_ref_violations(
    target: dict[str, Any], *, branch: str | None, head_sha: str | None
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    if target.get("branch") != branch:
        violations.append(
            {
                "rule": "branch-mismatch",
                "path": "target.branch",
                "expected": branch,
                "observed": target.get("branch"),
            }
        )
    if target.get("head_sha") != head_sha:
        violations.append(
            {
                "rule": "head-mismatch",
                "path": "target.head_sha",
                "expected": head_sha,
                "observed": target.get("head_sha"),
            }
        )
    return violations


def _git_provenance(root: Path) -> tuple[str | None, str | None, list[str]]:
    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

    try:
        branch = git("symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip() or None
        head_sha = git("rev-parse", "--verify", "HEAD").stdout.strip() or None
        status = git("status", "--porcelain=v1", "-z", "--untracked-files=all").stdout
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None, None, []
    dirty_paths: list[str] = []
    for entry in status.split("\0"):
        if len(entry) >= 4:
            dirty_paths.append(entry[3:].split(" -> ")[-1])
    return branch, head_sha, sorted(dirty_paths)


def _read_object(
    path: Path | None,
    *,
    label: str,
    missing_allowed: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if path is None or not path.is_file():
        if missing_allowed:
            return {}, []
        return {}, [{"rule": f"{label.replace(' ', '-')}-missing", "path": str(path)}]
    if path.is_symlink():
        return {}, [{"rule": f"{label.replace(' ', '-')}-symlink", "path": str(path)}]
    try:
        if path.stat().st_size > MAX_EVIDENCE_BYTES:
            return {}, [{"rule": f"{label.replace(' ', '-')}-too-large", "path": str(path)}]
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, [
            {"rule": f"{label.replace(' ', '-')}-invalid", "path": str(path), "error": str(error)}
        ]
    if not isinstance(value, dict):
        return {}, [{"rule": f"{label.replace(' ', '-')}-not-object", "path": str(path)}]
    return cast(dict[str, Any], value), []


def _sha256_path(path: Path | None) -> str | None:
    if path is None or not path.is_file() or path.is_symlink():
        return None
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _check(check_id: str, violations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": "passed" if not violations else "blocked",
        "violations": violations,
    }


def _object(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _object_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        cast(dict[str, Any], item) for item in cast(list[object], value) if isinstance(item, dict)
    ]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str) and item]


def _conditional_surface_ids(baseline: dict[str, Any]) -> list[str]:
    values = [
        *_string_list(baseline.get("conditional_on_add")),
        *_string_list(baseline.get("conditional")),
    ]
    return list(dict.fromkeys(values))


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)
