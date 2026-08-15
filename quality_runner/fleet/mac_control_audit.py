from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from quality_runner.fleet.contracts import digest
from quality_runner.fleet.mac_control_artifacts import read_json
from quality_runner.fleet.mac_control_contracts import (
    CRITERIA,
    MAC_CONTROL_EVIDENCE_SCHEMA,
    MAC_CONTROL_MANIFEST_RELATIVE_PATH,
    MAC_CONTROL_MANIFEST_SCHEMA,
    MAC_CONTROL_PREVIOUS_EVIDENCE_SCHEMA,
    evaluate_semantic_evidence,
    merge_task_evidence,
    normalize_applicability,
    semantic_source_paths,
    string_list,
    task_entries,
    validate_evidence_producer,
    validate_manifest,
)


def _audit_repository(
    repository: dict[str, Any],
    *,
    observed_at: str,
    live: bool,
    macctl_path: str,
    evidence_dir: Path | None,
    commit: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    repo_id = str(repository["repo_id"])
    manifest_path = Path(str(repository["primary_path"])) / MAC_CONTROL_MANIFEST_RELATIVE_PATH
    manifest = read_json(manifest_path)
    if manifest is None:
        return (
            _base_entry(
                repository,
                observed_at,
                commit,
                "",
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
    semantic_evaluation = evaluate_semantic_evidence(manifest_path.parent.parent, manifest)
    source_provenance = _source_provenance(manifest_path.parent.parent, manifest)
    if source_provenance["status"] == "dirty":
        dirty_paths = ", ".join(source_provenance["dirty_paths"])
        semantic_evaluation = {
            **semantic_evaluation,
            "grounding_errors": [
                *semantic_evaluation["grounding_errors"],
                "source provenance is dirty for commit-bound evidence: " + dirty_paths,
            ],
        }
    elif source_provenance["status"] == "unavailable":
        semantic_evaluation = {
            **semantic_evaluation,
            "grounding_errors": [
                *semantic_evaluation["grounding_errors"],
                "source provenance could not be verified against the repository worktree",
            ],
        }
    criteria = semantic_evaluation["criteria"]
    grounding_errors = semantic_evaluation["grounding_errors"]
    evidence = [f"manifest:{MAC_CONTROL_MANIFEST_RELATIVE_PATH.as_posix()}"]
    evidence.extend(semantic_evaluation["evidence"])
    live_evidence: list[str] = []
    live_errors: list[str] = []
    provider: dict[str, Any] | None = None
    sidecar = _load_evidence(evidence_dir, repo_id)
    if sidecar is not None:
        sidecar_schema = str(sidecar.get("schema", "")).strip()
        if sidecar_schema not in {
            MAC_CONTROL_EVIDENCE_SCHEMA,
            MAC_CONTROL_PREVIOUS_EVIDENCE_SCHEMA,
        }:
            evidence.append("evidence:invalid_schema")
            live_errors.append("evidence sidecar schema is invalid")
        else:
            if sidecar_schema == MAC_CONTROL_PREVIOUS_EVIDENCE_SCHEMA:
                live_errors.append(
                    f"{MAC_CONTROL_PREVIOUS_EVIDENCE_SCHEMA} is readable but cannot satisfy "
                    f"live measurement; produce {MAC_CONTROL_EVIDENCE_SCHEMA}"
                )
            if sidecar.get("repository_id") != repo_id:
                live_errors.append("evidence sidecar repository_id does not match the repository")
            if sidecar_schema == MAC_CONTROL_EVIDENCE_SCHEMA:
                live_errors.extend(validate_evidence_producer(sidecar.get("producer")))
            sidecar_evidence = string_list(sidecar.get("evidence"))
            evidence.extend(sidecar_evidence)
            live_evidence.extend(sidecar_evidence)
            if isinstance(sidecar.get("observed_at"), str) and sidecar["observed_at"].strip():
                observed_at = sidecar["observed_at"].strip()
            sidecar_commit = sidecar.get("observed_commit")
            if not isinstance(sidecar_commit, str) or not sidecar_commit.strip():
                live_errors.append("evidence sidecar observed_commit is required")
            elif sidecar_commit.strip() != commit:
                live_errors.append(
                    "evidence sidecar observed_commit does not match the repository commit"
                )
            if sidecar_schema == MAC_CONTROL_EVIDENCE_SCHEMA:
                source_digest = sidecar.get("observed_source_digest")
                if not isinstance(source_digest, str) or not source_digest.strip():
                    live_errors.append("evidence sidecar observed_source_digest is required")
                elif source_digest.strip() != source_provenance["digest"]:
                    live_errors.append(
                        "evidence sidecar observed_source_digest does not match audited source"
                    )
            merge_task_evidence(
                tasks,
                sidecar.get("tasks"),
                live_errors,
                evidence_schema=sidecar_schema,
            )
    if manifest_errors:
        evidence.extend(f"manifest_error:{error}" for error in manifest_errors)
    if grounding_errors:
        evidence.extend(f"grounding_error:{error}" for error in grounding_errors)
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
            str(manifest.get("schema", "")),
            applicability,
            reason,
            tasks,
            criteria,
            evidence,
            implementation_errors=manifest_errors,
            semantic_evaluation=semantic_evaluation,
            live_errors=live_errors,
            live_evidence=live_evidence,
            source_provenance=source_provenance,
        ),
        provider,
    )


def _base_entry(
    repository: dict[str, Any],
    observed_at: str,
    commit: str,
    manifest_schema: str,
    applicability: str,
    reason: str,
    tasks: list[dict[str, Any]],
    criteria: dict[str, bool],
    evidence: list[str],
    *,
    implementation_errors: list[str] | None = None,
    semantic_evaluation: dict[str, Any] | None = None,
    live_errors: list[str] | None = None,
    live_evidence: list[str] | None = None,
    source_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    implementation_errors = sorted(set(implementation_errors or []))
    semantic_evaluation = semantic_evaluation or {
        "evidence_level": "not_source_grounded",
        "criteria": {},
        "criteria_passed_count": 0,
        "criteria_total": len(CRITERIA) if applicability == "applicable" else 0,
        "declaration_criteria_count": 0,
        "dimension_states": {},
        "grounding_errors": [],
        "evidence": [],
    }
    grounding_errors = sorted(set(semantic_evaluation.get("grounding_errors", [])))
    live_errors = sorted(set(live_errors or []))
    live_evidence = sorted(set(live_evidence or []))
    source_provenance = source_provenance or {
        "status": "unavailable",
        "digest": "",
        "paths": [],
        "dirty_paths": [],
    }
    implementation_evidence = sorted(
        item for item in set(evidence) if item.startswith("manifest:") or item.startswith("source:")
    )
    criteria_passed_count = int(semantic_evaluation.get("criteria_passed_count", 0))
    criteria_total = int(semantic_evaluation.get("criteria_total", 0))
    all_implementation_errors = sorted(set(implementation_errors + grounding_errors))
    return {
        "repository_id": str(repository["repo_id"]),
        "repository_name": Path(str(repository["primary_path"])).name,
        "manifest_schema": manifest_schema,
        "applicability": applicability,
        "applicability_reason": reason,
        "observed_at": observed_at,
        "observed_commit": commit,
        "source_provenance": source_provenance,
        "criteria": dict(sorted(criteria.items())),
        "supported_tasks": tasks,
        "validation_errors": all_implementation_errors,
        "evidence": sorted(set(evidence)),
        "implementation_contract": {
            "status": _implementation_status(
                applicability,
                implementation_errors,
                grounding_errors,
                manifest_schema,
                criteria_passed_count,
                criteria_total,
            ),
            "criteria": dict(sorted(criteria.items())),
            "criteria_passed_count": criteria_passed_count,
            "criteria_total": criteria_total,
            "declaration_criteria_count": int(
                semantic_evaluation.get("declaration_criteria_count", 0)
            ),
            "evidence_level": str(semantic_evaluation.get("evidence_level", "")),
            "dimension_states": semantic_evaluation.get("dimension_states", {}),
            "validation_errors": all_implementation_errors,
            "grounding_errors": grounding_errors,
            "evidence": implementation_evidence,
        },
        "live_task_evidence": _live_task_evidence(
            applicability,
            tasks,
            live_errors,
            live_evidence,
        ),
    }


def _implementation_status(
    applicability: str,
    errors: list[str],
    grounding_errors: list[str],
    manifest_schema: str,
    criteria_passed_count: int,
    criteria_total: int,
) -> str:
    if applicability == "not_applicable":
        return "failed" if errors else "not_applicable"
    if applicability != "applicable":
        return "blocked"
    if errors:
        return "failed"
    if manifest_schema.strip() != MAC_CONTROL_MANIFEST_SCHEMA:
        return "review_required"
    if grounding_errors or criteria_passed_count != criteria_total or criteria_total == 0:
        return "review_required"
    return "passed"


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
        and task.get("measurement_valid") is True
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


def _source_provenance(repository_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    paths = semantic_source_paths(manifest)
    snapshots: list[dict[str, str]] = []
    for relative_path in paths:
        path = repository_root / relative_path
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            content = "<unavailable>"
        snapshots.append({"path": relative_path, "digest": digest(content)})
    try:
        completed = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                *paths,
            ],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    if completed is None or completed.returncode != 0:
        status = "unavailable"
        dirty_paths: list[str] = []
    else:
        dirty_paths = sorted(
            line[3:].strip()
            for line in completed.stdout.splitlines()
            if len(line) >= 4 and line[3:].strip()
        )
        status = "dirty" if dirty_paths else "clean"
    return {
        "status": status,
        "digest": digest(snapshots),
        "paths": paths,
        "dirty_paths": dirty_paths,
    }


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
