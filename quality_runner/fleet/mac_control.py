from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import digest, parse_as_of, stable_id
from quality_runner.fleet.discovery import discover_repositories, repository_record_for_root
from quality_runner.fleet.mac_control_artifacts import (
    artifact_root,
    build_summary,
    mac_control_feed_payload,
    mac_control_replay_payload,
    mac_control_report_payload,
    read_json,
    write_artifacts,
)
from quality_runner.fleet.mac_control_contracts import (
    CRITERIA,
    MAC_CONTROL_AUDIT_SCHEMA,
    MAC_CONTROL_EVIDENCE_SCHEMA,
    MAC_CONTROL_MANIFEST_RELATIVE_PATH,
    MAC_CONTROL_MANIFEST_SCHEMA,
    MAC_CONTROL_REPORT_SCHEMA,
    MacControlAuditError,
    bool_mapping,
    merge_task_evidence,
    normalize_applicability,
    string_list,
    task_entries,
    validate_manifest,
)

__all__ = [
    "MAC_CONTROL_MANIFEST_SCHEMA",
    "mac_control_audit_payload",
    "mac_control_feed_payload",
    "mac_control_report_payload",
    "mac_control_replay_payload",
    "validate_manifest",
]


def mac_control_audit_payload(
    *,
    projects_root: Path,
    output_dir: Path | None = None,
    repository_paths: list[Path] | None = None,
    as_of: str | None = None,
    live: bool = False,
    macctl_path: str = "macctl",
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_as_of = parse_as_of(as_of)
    root = projects_root.expanduser().resolve()
    repositories = _repositories_for_scope(root, repository_paths)
    audit_id = stable_id(
        "mac-control",
        str(root),
        resolved_as_of,
        live,
        macctl_path if live else None,
        str(evidence_dir.expanduser().resolve()) if evidence_dir else None,
        sorted(str(path.expanduser().resolve()) for path in repository_paths or []),
    )
    artifact_dir = artifact_root(output_dir, audit_id)
    entries: list[dict[str, Any]] = []
    provider_results: dict[str, dict[str, Any]] = {}
    for repository in repositories:
        entry, provider = _audit_repository(
            repository,
            observed_at=resolved_as_of,
            live=live,
            macctl_path=macctl_path,
            evidence_dir=evidence_dir,
        )
        entries.append(entry)
        if provider is not None:
            provider_results[str(repository["repo_id"])] = provider

    report = {
        "schema_version": MAC_CONTROL_REPORT_SCHEMA,
        "producer": "mac-control",
        "run_id": audit_id,
        "observed_at": resolved_as_of,
        # Pronto evaluates its current maturity-applicable subset.  QR keeps
        # the broader fleet inventory so the denominator is auditable.
        "scope": "quality_runner_fleet",
        "repositories": entries,
    }
    summary = build_summary(
        audit_id=audit_id,
        observed_at=resolved_as_of,
        projects_root=root,
        repositories=entries,
        live=live,
    )
    inventory = {
        "schema": MAC_CONTROL_AUDIT_SCHEMA,
        "audit_id": audit_id,
        "as_of": resolved_as_of,
        "projects_root": str(root),
        "scope": (
            "explicit repository paths under the bounded projects root"
            if repository_paths is not None
            else "all repository identities under the bounded projects root"
        ),
        "manifest_path": str(MAC_CONTROL_MANIFEST_RELATIVE_PATH),
        "live_policy": {
            "requested": live,
            "provider": "mac-control",
            "macctl_path": macctl_path if live else None,
            "gui_execution_implicit": False,
        },
        "evidence_dir": str(evidence_dir.expanduser().resolve()) if evidence_dir else None,
        "repositories": [
            {
                "repo_id": repository["repo_id"],
                "primary_path": repository["primary_path"],
                "observed_commit": _repository_commit(repository),
            }
            for repository in repositories
        ],
        "provenance_hash": digest(
            {
                "audit_id": audit_id,
                "as_of": resolved_as_of,
                "repositories": [
                    {"repo_id": entry["repository_id"], "commit": entry["observed_commit"]}
                    for entry in entries
                ],
            }
        ),
    }
    paths = write_artifacts(
        artifact_root=artifact_dir,
        inventory=inventory,
        report=report,
        summary=summary,
        provider_results=provider_results,
    )
    return {
        "schema": MAC_CONTROL_AUDIT_SCHEMA,
        "status": "completed" if entries else "blocked",
        "audit_id": audit_id,
        "as_of": resolved_as_of,
        "repository_count": len(entries),
        "artifact_root": str(artifact_dir),
        "artifact_paths": paths,
        "summary": summary,
        "report": report,
        "implementation_allowed": False,
    }


def _audit_repository(
    repository: dict[str, Any],
    *,
    observed_at: str,
    live: bool,
    macctl_path: str,
    evidence_dir: Path | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    repo_id = str(repository["repo_id"])
    commit = _repository_commit(repository)
    manifest_path = Path(str(repository["primary_path"])) / MAC_CONTROL_MANIFEST_RELATIVE_PATH
    manifest = read_json(manifest_path)
    if manifest is None:
        return (
            _base_entry(
                repository,
                observed_at,
                commit,
                "unknown",
                "No repository-owned Mac Control manifest was found.",
                [],
                {},
                [],
                implementation_errors=["No repository-owned Mac Control manifest was found."],
                live_errors=["No repository-owned Mac Control manifest was found."],
            ),
            None,
        )
    manifest_errors = validate_manifest(manifest)
    if manifest.get("repository_id") != repo_id:
        manifest_errors.append("repository_id does not match the discovered repository identity")
    applicability = normalize_applicability(manifest.get("applicability")) or "unknown"
    reason = str(manifest.get("applicability_reason", "")).strip() or "Manifest validation failed."
    tasks = task_entries(manifest.get("tasks"))
    criteria = bool_mapping(manifest.get("criteria"))
    evidence = [f"manifest:{MAC_CONTROL_MANIFEST_RELATIVE_PATH.as_posix()}"]
    live_evidence: list[str] = []
    live_errors: list[str] = []
    provider: dict[str, Any] | None = None
    sidecar = _load_evidence(evidence_dir, repo_id)
    if sidecar is not None:
        if sidecar.get("schema") != MAC_CONTROL_EVIDENCE_SCHEMA:
            evidence.append("evidence:invalid_schema")
            live_errors.append("evidence sidecar schema is invalid")
        else:
            if sidecar.get("repository_id") != repo_id:
                live_errors.append("evidence sidecar repository_id does not match the repository")
            sidecar_evidence = string_list(sidecar.get("evidence"))
            evidence.extend(sidecar_evidence)
            live_evidence.extend(sidecar_evidence)
            if isinstance(sidecar.get("observed_at"), str) and sidecar["observed_at"].strip():
                observed_at = sidecar["observed_at"].strip()
            sidecar_commit = sidecar.get("observed_commit")
            if (
                isinstance(sidecar_commit, str)
                and sidecar_commit.strip()
                and sidecar_commit.strip() != commit
            ):
                live_errors.append(
                    "evidence sidecar observed_commit does not match the repository commit"
                )
            merge_task_evidence(tasks, sidecar.get("tasks"), live_errors)
    if manifest_errors:
        evidence.extend(f"manifest_error:{error}" for error in manifest_errors)
    if live_errors:
        evidence.extend(f"live_error:{error}" for error in live_errors)
    if live and applicability == "applicable" and not manifest_errors:
        provider = _run_mac_control_provider(macctl_path, manifest_path, manifest)
        provider_passed = (
            provider.get("status") == "succeeded"
            and provider.get("exit_code") == 0
            and provider.get("structural_valid") is True
            and provider.get("redacted") is True
        )
        if provider_passed:
            structural_evidence = "macctl:ideal-state.audit:structural_pass"
            evidence.append(structural_evidence)
            live_evidence.append(structural_evidence)
        else:
            provider_evidence = f"macctl:ideal-state.audit:{provider.get('status', 'unknown')}"
            evidence.append(provider_evidence)
            live_evidence.append(provider_evidence)
            live_errors.append(
                "live Mac Control ideal-state audit did not produce a redacted structural pass"
            )
        if provider.get("finding_count", 0):
            findings_evidence = f"macctl:ideal-state.audit:findings={provider['finding_count']}"
            evidence.append(findings_evidence)
            live_evidence.append(findings_evidence)
    if applicability == "not_applicable" and not manifest_errors:
        tasks = []
        criteria = {}
        live_errors = []
        live_evidence = []
    return (
        _base_entry(
            repository,
            observed_at,
            commit,
            applicability,
            reason,
            tasks,
            criteria,
            evidence,
            implementation_errors=manifest_errors,
            live_errors=live_errors,
            live_evidence=live_evidence,
        ),
        provider,
    )


def _base_entry(
    repository: dict[str, Any],
    observed_at: str,
    commit: str,
    applicability: str,
    reason: str,
    tasks: list[dict[str, Any]],
    criteria: dict[str, bool],
    evidence: list[str],
    *,
    implementation_errors: list[str] | None = None,
    live_errors: list[str] | None = None,
    live_evidence: list[str] | None = None,
) -> dict[str, Any]:
    implementation_errors = sorted(set(implementation_errors or []))
    live_errors = sorted(set(live_errors or []))
    live_evidence = sorted(set(live_evidence or []))
    implementation_evidence = sorted(item for item in set(evidence) if item.startswith("manifest:"))
    return {
        "repository_id": str(repository["repo_id"]),
        "repository_name": Path(str(repository["primary_path"])).name,
        "applicability": applicability,
        "applicability_reason": reason,
        "observed_at": observed_at,
        "observed_commit": commit,
        "criteria": dict(sorted(criteria.items())),
        "supported_tasks": tasks,
        "validation_errors": implementation_errors,
        "evidence": sorted(set(evidence)),
        "implementation_contract": {
            "status": _implementation_status(applicability, implementation_errors),
            "criteria": dict(sorted(criteria.items())),
            "criteria_passed_count": sum(
                1
                for criterion in CRITERIA
                if applicability == "applicable" and criteria.get(criterion) is True
            ),
            "criteria_total": len(CRITERIA) if applicability == "applicable" else 0,
            "validation_errors": implementation_errors,
            "evidence": implementation_evidence,
        },
        "live_task_evidence": _live_task_evidence(
            applicability,
            tasks,
            live_errors,
            live_evidence,
        ),
    }


def _implementation_status(applicability: str, errors: list[str]) -> str:
    if applicability == "not_applicable":
        return "failed" if errors else "not_applicable"
    if applicability != "applicable":
        return "blocked"
    return "failed" if errors else "passed"


def _live_task_evidence(
    applicability: str,
    tasks: list[dict[str, Any]],
    errors: list[str],
    evidence: list[str],
) -> dict[str, Any]:
    if applicability == "not_applicable":
        status = "not_applicable"
    elif applicability != "applicable" or errors:
        status = "blocked"
    elif tasks and any(_task_has_failed_attempt(task) for task in tasks):
        status = "failed"
    else:
        status = (
            "passed"
            if all(_task_is_measured(task) for task in tasks) and tasks
            else "review_required"
        )
    failure_reasons = list(errors)
    for task in tasks:
        if not _task_is_measured(task):
            failure_reasons.append(
                f"task {task.get('task_id') or 'unnamed'} route measurement is incomplete "
                f"({task.get('successes', 0)}/{task.get('attempts', 0)})"
            )
    return {
        "status": status,
        "task_count": len(tasks),
        "measured_task_count": sum(1 for task in tasks if _task_is_measured(task)),
        "attempt_count": sum(
            task.get("attempts", 0)
            for task in tasks
            if isinstance(task.get("attempts"), int) and task.get("attempts", 0) >= 0
        ),
        "success_count": sum(
            task.get("successes", 0)
            for task in tasks
            if isinstance(task.get("successes"), int) and task.get("successes", 0) >= 0
        ),
        "failure_reasons": sorted(set(failure_reasons)),
        "evidence": sorted(set(evidence)),
    }


def _task_is_measured(task: dict[str, Any]) -> bool:
    attempts = task.get("attempts")
    successes = task.get("successes")
    return (
        isinstance(attempts, int)
        and attempts > 0
        and isinstance(successes, int)
        and successes == attempts
        and bool(task.get("evidence"))
    )


def _task_has_failed_attempt(task: dict[str, Any]) -> bool:
    attempts = task.get("attempts")
    successes = task.get("successes")
    return (
        isinstance(attempts, int)
        and attempts > 0
        and isinstance(successes, int)
        and successes != attempts
    )


def _load_evidence(evidence_dir: Path | None, repo_id: str) -> dict[str, Any] | None:
    if evidence_dir is None:
        return None
    return read_json(evidence_dir.expanduser() / f"{repo_id}.json")


def _run_mac_control_provider(
    macctl_path: str, manifest_path: Path, manifest: dict[str, Any]
) -> dict[str, Any]:
    app = manifest.get("app")
    app_name = app.get("name") if isinstance(app, dict) else None
    if not isinstance(app_name, str) or not app_name.strip():
        return {
            "status": "blocked",
            "structural_valid": False,
            "finding_count": 0,
            "reason": "manifest app.name is missing",
        }
    try:
        completed = subprocess.run(
            [
                macctl_path,
                "ideal-state",
                "audit",
                "--app",
                app_name,
                "--manifest",
                str(manifest_path),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "status": "unavailable",
            "structural_valid": False,
            "finding_count": 0,
            "reason": type(error).__name__,
        }
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        return {
            "status": "failed",
            "structural_valid": False,
            "finding_count": 0,
            "reason": "provider returned invalid JSON",
        }
    result = payload.get("result") if isinstance(payload, dict) else None
    result = result if isinstance(result, dict) else {}
    findings = result.get("findings")
    return {
        "status": str(payload.get("status", "failed")) if isinstance(payload, dict) else "failed",
        "structural_valid": result.get("structural_valid") is True,
        "finding_count": len(findings) if isinstance(findings, list) else 0,
        "redacted": result.get("redacted") is True,
        "exit_code": completed.returncode,
    }


def _repositories_for_scope(
    root: Path, repository_paths: list[Path] | None
) -> list[dict[str, Any]]:
    if repository_paths is None:
        return discover_repositories(root)
    records: dict[str, dict[str, Any]] = {}
    for path in repository_paths:
        resolved = path.expanduser().resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise MacControlAuditError(
                f"repository path is outside the bounded projects root: {resolved}"
            ) from error
        record = repository_record_for_root(resolved)
        records[str(record["repo_id"])] = record
    return [records[key] for key in sorted(records)]


def _repository_commit(repository: dict[str, Any]) -> str:
    for checkout in repository.get("checkouts", []):
        if (
            isinstance(checkout, dict)
            and checkout.get("is_primary")
            and isinstance(checkout.get("head"), str)
        ):
            return checkout["head"]
    for checkout in repository.get("checkouts", []):
        if isinstance(checkout, dict) and isinstance(checkout.get("head"), str):
            return checkout["head"]
    return ""
