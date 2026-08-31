from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from quality_runner.artifacts import existing_artifact_dir, prepare_artifact_dir, safe_child_file
from quality_runner.task_check_projection import finalize_task_check, required_readiness_blockers
from quality_runner.task_contract import (
    TASK_ANALYSIS_MODE,
    TASK_CACHE_MODE,
    TASK_CHECK_MODE_AUTHORITATIVE,
    TASK_RELEASE_ENFORCEMENT_REQUIRED,
    contract_hashes,
    drift_blockers,
)
from quality_runner.task_findings import promotion_issues
from quality_runner.task_readiness import evaluate_readiness
from quality_runner.task_snapshot import changed_paths, workspace_snapshot
from quality_runner.workflow_internal import generated_run_id


def reusable_authoritative_check(
    *,
    repo_root: Path,
    task_id: str,
    record: dict[str, Any],
    baseline: dict[str, Any],
    config: dict[str, Any],
    prevention: dict[str, Any],
) -> dict[str, Any] | None:
    include_paths = tuple(
        item for item in prevention.get("snapshot_include_paths", []) if isinstance(item, str)
    )
    baseline_source = cast(dict[str, Any], baseline.get("source", {}))
    merge_target_ref = (
        str(baseline_source["head_sha"])
        if baseline_source.get("kind") == "git_revision"
        and isinstance(baseline_source.get("head_sha"), str)
        else None
    )
    with workspace_snapshot(
        repo_root,
        merge_target_ref=merge_target_ref,
        include_paths=include_paths,
    ) as (_snapshot_root, snapshot):
        readiness = evaluate_readiness(repo_root=repo_root, prevention=prevention)
    expected_evidence = {
        **contract_hashes(repo_root, config),
        "toolchain_hash": readiness["toolchain_hash"],
        "task_analysis_mode": TASK_ANALYSIS_MODE,
        "task_cache_mode": TASK_CACHE_MODE,
    }
    if (
        _repository_blockers(baseline, snapshot)
        or drift_blockers(baseline, repo_root, config, readiness)
        or promotion_issues(prevention)
        or required_readiness_blockers(readiness)
    ):
        return None
    digest = str(snapshot.get("snapshot_digest"))
    for source_run_id in reversed(cast(list[str], record.get("checks", []))):
        candidate = _load_candidate(repo_root, source_run_id)
        if candidate is None or not _candidate_matches(candidate, digest, expected_evidence):
            continue
        gate_results = cast(list[dict[str, Any]], candidate.get("gate_results", []))
        if any(
            item.get("required") is True and item.get("status") != "passed" for item in gate_results
        ):
            continue
        run_id = f"{generated_run_id()}-task-release-check"
        return finalize_task_check(
            repo_root=repo_root,
            config=config,
            run_dir=prepare_artifact_dir(repo_root, run_id),
            task_id=task_id,
            run_id=run_id,
            baseline_run_id=str(record["baseline_run_id"]),
            check_mode=TASK_CHECK_MODE_AUTHORITATIVE,
            release_enforcement=TASK_RELEASE_ENFORCEMENT_REQUIRED,
            snapshot=snapshot,
            changed_paths=changed_paths(cast(dict[str, Any], baseline["snapshot"]), snapshot),
            findings=cast(dict[str, Any], candidate["normalized_findings"]),
            delta=cast(dict[str, Any], candidate["delta"]),
            readiness=readiness,
            gate_results=gate_results,
            repository_blockers=[],
            contract_blockers=[],
            promotion_blockers=[],
            gate_blockers=[],
            readiness_blockers=[],
            analysis_evidence=cast(dict[str, Any], candidate["analysis"]),
            reused_from_run_id=source_run_id,
        )
    return None


def _load_candidate(repo_root: Path, run_id: str) -> dict[str, Any] | None:
    try:
        directory = existing_artifact_dir(repo_root, run_id)
        path = safe_child_file(directory, "task-check.json", require_exists=True)
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return None


def _candidate_matches(
    candidate: dict[str, Any], digest: str, expected_evidence: dict[str, Any]
) -> bool:
    release = candidate.get("release_readiness")
    snapshot = candidate.get("snapshot")
    return bool(
        candidate.get("status") == "pass"
        and candidate.get("mode") == TASK_CHECK_MODE_AUTHORITATIVE
        and isinstance(release, dict)
        and release.get("eligible") is True
        and isinstance(snapshot, dict)
        and snapshot.get("snapshot_digest") == digest
        and candidate.get("evidence") == expected_evidence
    )


def _repository_blockers(
    baseline: dict[str, Any], snapshot: dict[str, Any]
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
