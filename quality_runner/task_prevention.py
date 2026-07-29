from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from quality_runner.application.read_only_audit import analyze_read_only_audit
from quality_runner.artifacts import (
    existing_artifact_dir,
    prepare_artifact_dir,
    prepare_directory,
    safe_child_file,
    validate_path_segment,
    write_json,
    write_text,
)
from quality_runner.config import CONFIG_FILE_NAME, load_repo_config
from quality_runner.core.audit_contracts import AuditRequest
from quality_runner.schema_constants import (
    TASK_BASELINE_SCHEMA,
    TASK_CHECK_SCHEMA,
    TASK_RECORD_SCHEMA,
)
from quality_runner.task_contract import (
    contract_hashes,
    deduplicate_blockers,
    drift_blockers,
    render_task_check_markdown,
)
from quality_runner.task_findings import (
    compare_findings,
    normalize_findings,
    promotion_issues,
)
from quality_runner.task_readiness import (
    evaluate_readiness,
    required_gate_failures,
    run_certified_gates,
)
from quality_runner.task_snapshot import (
    SnapshotError,
    attach_git_metadata,
    changed_paths,
    workspace_snapshot,
)
from quality_runner.workflow_internal import generated_run_id


def task_command_payload(args: Any) -> dict[str, Any]:
    repo_root = Path(args.repo_path).expanduser().resolve()
    try:
        if args.task_action == "start":
            return start_task(
                repo_root,
                task_id=args.task_id,
                baseline_ref=args.baseline_ref,
                intent_path=Path(args.intent).expanduser() if args.intent else None,
            )
        if args.task_action == "check":
            return check_task(repo_root, task_id=args.task_id)
        if args.task_action == "rebaseline":
            return rebaseline_task(repo_root, task_id=args.task_id, reason=args.reason)
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        return _error_payload("invalid", "invalid_task_contract", str(error))
    except (SnapshotError, OSError) as error:
        return _error_payload("blocked", "workspace_evidence_unavailable", str(error))
    return _error_payload("invalid", "invalid_task_action", "unknown task action")


def start_task(
    repo_root: Path,
    *,
    task_id: str,
    baseline_ref: str | None,
    intent_path: Path | None,
) -> dict[str, Any]:
    _validate_task_id(task_id)
    config = load_repo_config(repo_root)
    if config.get("warnings"):
        return _invalid_config(config)
    if _task_record_path(repo_root, task_id).exists():
        return _error_payload(
            "invalid",
            "task_already_exists",
            f"task {task_id} already exists; use task rebaseline to preserve lineage",
        )
    run_id = f"{generated_run_id()}-task-start"
    baseline = _capture_baseline(
        repo_root,
        task_id=task_id,
        run_id=run_id,
        baseline_ref=baseline_ref,
        intent=_intent_payload(repo_root, intent_path),
        reason=None,
        supersedes=None,
    )
    record = {
        "schema": TASK_RECORD_SCHEMA,
        "task_id": task_id,
        "repository": baseline["repository"],
        "baseline_run_id": run_id,
        "lineage": [run_id],
        "checks": [],
    }
    _write_task_record(repo_root, task_id, record)
    return {
        "schema": TASK_BASELINE_SCHEMA,
        "status": "started",
        "task_id": task_id,
        "baseline_run_id": run_id,
        "source": baseline["source"],
        "snapshot_digest": baseline["snapshot"]["snapshot_digest"],
        "coverage": baseline["coverage"],
        "evidence": baseline["evidence"],
    }


def rebaseline_task(repo_root: Path, *, task_id: str, reason: str) -> dict[str, Any]:
    _validate_task_id(task_id)
    if not reason.strip():
        return _error_payload("invalid", "missing_rebaseline_reason", "reason must not be empty")
    record = _load_task_record(repo_root, task_id)
    config = load_repo_config(repo_root)
    if config.get("warnings"):
        return _invalid_config(config)
    previous = str(record["baseline_run_id"])
    previous_baseline = _load_run_json(
        repo_root,
        previous,
        "task-baseline.json",
    )
    previous_source = cast(dict[str, Any], previous_baseline.get("source", {}))
    baseline_ref = (
        str(previous_source["head_sha"])
        if previous_source.get("kind") == "git_revision"
        and isinstance(previous_source.get("head_sha"), str)
        else None
    )
    run_id = f"{generated_run_id()}-task-rebaseline"
    baseline = _capture_baseline(
        repo_root,
        task_id=task_id,
        run_id=run_id,
        baseline_ref=baseline_ref,
        intent=None,
        reason=reason.strip(),
        supersedes=previous,
    )
    lineage = [*cast(list[str], record.get("lineage", [])), run_id]
    record.update({"baseline_run_id": run_id, "lineage": lineage})
    _write_task_record(repo_root, task_id, record)
    return {
        "schema": TASK_BASELINE_SCHEMA,
        "status": "rebaselined",
        "task_id": task_id,
        "baseline_run_id": run_id,
        "supersedes": previous,
        "reason": reason.strip(),
        "source": baseline["source"],
        "snapshot_digest": baseline["snapshot"]["snapshot_digest"],
        "coverage": baseline["coverage"],
        "evidence": baseline["evidence"],
    }


def check_task(repo_root: Path, *, task_id: str) -> dict[str, Any]:
    _validate_task_id(task_id)
    record = _load_task_record(repo_root, task_id)
    baseline_run_id = str(record["baseline_run_id"])
    baseline = _load_run_json(repo_root, baseline_run_id, "task-baseline.json")
    config = load_repo_config(repo_root)
    if config.get("warnings"):
        return _invalid_config(config)
    prevention = _prevention(config)
    run_id = f"{generated_run_id()}-task-check"
    run_dir = prepare_artifact_dir(repo_root, run_id)

    include_paths = tuple(
        item for item in prevention.get("snapshot_include_paths", []) if isinstance(item, str)
    )
    with workspace_snapshot(repo_root, include_paths=include_paths) as (snapshot_root, snapshot):
        analysis = _analyze(snapshot_root, run_id)
        findings = normalize_findings(
            code_quality_scan=cast(dict[str, Any], analysis.code_quality_scan),
            security_scan=cast(dict[str, Any], analysis.security_scan),
            prevention=prevention,
        )
        readiness = evaluate_readiness(repo_root=repo_root, prevention=prevention)
        if any(gate.get("state") == "certified" for gate in readiness["gates"]):
            attach_git_metadata(repo_root, snapshot_root)
        gate_results, gate_blockers = run_certified_gates(
            snapshot_root=snapshot_root,
            repo_root=repo_root,
            readiness=readiness,
        )

    changed = changed_paths(cast(dict[str, Any], baseline["snapshot"]), snapshot)
    delta = compare_findings(
        baseline=cast(dict[str, Any], baseline["normalized_findings"]),
        current=findings,
        changed_paths=changed,
        dispositions=cast(list[dict[str, Any]], config.get("accepted_dispositions", [])),
        required_modules=cast(list[str], prevention.get("required_modules", [])),
    )
    blockers = [
        *_repository_blockers(baseline, snapshot),
        *drift_blockers(baseline, repo_root, config, readiness),
        *promotion_issues(prevention),
        *cast(list[dict[str, str]], delta["blockers"]),
        *gate_blockers,
        *_required_readiness_blockers(readiness),
    ]
    failures = required_gate_failures(gate_results)
    decision = (
        "blocked"
        if blockers
        else "violation"
        if delta["counts"]["new_enforced"] or failures
        else "pass"
    )
    payload = {
        "schema": TASK_CHECK_SCHEMA,
        "status": decision,
        "task_id": task_id,
        "run_id": run_id,
        "baseline_run_id": baseline_run_id,
        "repository": snapshot["repository"],
        "snapshot": snapshot,
        "changed_paths": changed,
        "coverage": findings["coverage"],
        "normalized_findings": findings,
        "delta": delta,
        "prevention_readiness": readiness,
        "gate_results": gate_results,
        "required_gate_failures": failures,
        "blockers": deduplicate_blockers(blockers),
        "evidence": {
            **contract_hashes(repo_root, config),
            "toolchain_hash": readiness["toolchain_hash"],
        },
    }
    write_json(safe_child_file(run_dir, "workspace-snapshot.json"), snapshot)
    write_json(safe_child_file(run_dir, "normalized-findings.json"), findings)
    write_json(safe_child_file(run_dir, "prevention-readiness.json"), readiness)
    write_json(safe_child_file(run_dir, "task-check.json"), payload)
    write_text(safe_child_file(run_dir, "task-check.md"), render_task_check_markdown(payload))
    checks = [*cast(list[str], record.get("checks", [])), run_id]
    record.update({"checks": checks, "last_status": decision})
    _write_task_record(repo_root, task_id, record)
    return payload


def _capture_baseline(
    repo_root: Path,
    *,
    task_id: str,
    run_id: str,
    baseline_ref: str | None,
    intent: dict[str, Any] | None,
    reason: str | None,
    supersedes: str | None,
) -> dict[str, Any]:
    config = load_repo_config(repo_root)
    prevention = _prevention(config)
    run_dir = prepare_artifact_dir(repo_root, run_id)
    include_paths = tuple(
        item for item in prevention.get("snapshot_include_paths", []) if isinstance(item, str)
    )
    with workspace_snapshot(
        repo_root,
        baseline_ref=baseline_ref,
        include_paths=include_paths,
    ) as (snapshot_root, snapshot):
        if baseline_ref is not None:
            _overlay_config(repo_root, snapshot_root)
        analysis = _analyze(snapshot_root, run_id)
        findings = normalize_findings(
            code_quality_scan=cast(dict[str, Any], analysis.code_quality_scan),
            security_scan=cast(dict[str, Any], analysis.security_scan),
            prevention=prevention,
        )
    readiness = evaluate_readiness(repo_root=repo_root, prevention=prevention)
    evidence = {
        **contract_hashes(repo_root, config),
        "toolchain_hash": readiness["toolchain_hash"],
    }
    baseline = {
        "schema": TASK_BASELINE_SCHEMA,
        "task_id": task_id,
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "repository": snapshot["repository"],
        "source": snapshot["source"],
        "snapshot": snapshot,
        "normalized_findings": findings,
        "coverage": findings["coverage"],
        "prevention_readiness": readiness,
        "evidence": evidence,
        "intent": intent,
        "reason": reason,
        "supersedes": supersedes,
        "analysis_policy_overlay": baseline_ref is not None,
    }
    write_json(safe_child_file(run_dir, "workspace-snapshot.json"), snapshot)
    write_json(safe_child_file(run_dir, "normalized-findings.json"), findings)
    write_json(safe_child_file(run_dir, "prevention-readiness.json"), readiness)
    write_json(safe_child_file(run_dir, "task-baseline.json"), baseline)
    return baseline


def _analyze(snapshot_root: Path, run_id: str) -> Any:
    request = AuditRequest(
        repo_root=snapshot_root,
        run_id=run_id,
        profile=None,
        ci_status_json=None,
        include_ignored_paths=(),
        branch_warnings=(),
        skill_review_report=None,
        intent=None,
    )
    return analyze_read_only_audit(request)


def _required_readiness_blockers(readiness: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for gate in readiness.get("gates", []):
        if (
            isinstance(gate, dict)
            and gate.get("required") is True
            and gate.get("state") != "certified"
        ):
            blockers.append(
                {
                    "code": "required_gate_not_ready",
                    "message": f"required gate {gate.get('id')} is {gate.get('state')}",
                }
            )
    return blockers


def _prevention(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("prevention")
    return value if isinstance(value, dict) else {}


def _overlay_config(repo_root: Path, snapshot_root: Path) -> None:
    source = repo_root / CONFIG_FILE_NAME
    target = snapshot_root / CONFIG_FILE_NAME
    if source.is_file():
        shutil.copyfile(source, target)
    elif target.exists():
        target.unlink()


def _intent_payload(repo_root: Path, path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    resolved = path.resolve()
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError("intent must be a readable regular file")
    content = resolved.read_bytes()
    return {
        "path": str(resolved),
        "repository_relative_path": _relative_or_none(repo_root, resolved),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _relative_or_none(root: Path, path: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def _task_record_path(repo_root: Path, task_id: str) -> Path:
    directory = prepare_directory(repo_root, ".quality-runner", "tasks")
    return safe_child_file(directory, f"{task_id}.json")


def _write_task_record(repo_root: Path, task_id: str, payload: dict[str, Any]) -> None:
    write_json(_task_record_path(repo_root, task_id), payload)


def _load_task_record(repo_root: Path, task_id: str) -> dict[str, Any]:
    path = _task_record_path(repo_root, task_id)
    if not path.is_file():
        raise FileNotFoundError(f"task {task_id} has not been started")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != TASK_RECORD_SCHEMA:
        raise ValueError(f"task {task_id} record has an unsupported schema")
    return cast(dict[str, Any], payload)


def _load_run_json(repo_root: Path, run_id: str, filename: str) -> dict[str, Any]:
    path = safe_child_file(existing_artifact_dir(repo_root, run_id), filename, require_exists=True)
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _validate_task_id(task_id: str) -> None:
    validate_path_segment(task_id, label="task_id")
    if task_id.endswith("."):
        raise ValueError("task_id must not end with a period")


def _invalid_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": TASK_CHECK_SCHEMA,
        "status": "invalid",
        "error": {
            "code": "invalid_prevention_configuration",
            "message": "Quality Runner configuration contains warnings",
        },
        "warnings": config.get("warnings", []),
    }


def _error_payload(status: str, code: str, message: str) -> dict[str, Any]:
    return {
        "schema": TASK_CHECK_SCHEMA,
        "status": status,
        "error": {"code": code, "message": message},
    }


def _repository_blockers(
    baseline: dict[str, Any],
    snapshot: dict[str, Any],
) -> list[dict[str, str]]:
    baseline_repo = cast(dict[str, Any], baseline.get("repository", {}))
    current_repo = cast(dict[str, Any], snapshot.get("repository", {}))
    if baseline_repo.get("identity") == current_repo.get("identity"):
        return []
    return [
        {
            "code": "repository_identity_mismatch",
            "message": "task baseline belongs to a different Git repository",
        }
    ]
