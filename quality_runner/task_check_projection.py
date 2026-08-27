from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from quality_runner.artifacts import safe_child_file, write_json, write_text
from quality_runner.schema_constants import TASK_CHECK_SCHEMA
from quality_runner.task_contract import (
    TASK_ANALYSIS_MODE,
    TASK_CACHE_MODE,
    contract_hashes,
    deduplicate_blockers,
    enforce_release_eligibility,
    release_readiness,
    render_task_check_markdown,
    task_next_action,
)
from quality_runner.task_readiness import required_gate_failures


def analysis_evidence(analysis: Any) -> dict[str, Any]:
    scan = cast(dict[str, Any], analysis.scan)
    return {
        "analysis_mode": TASK_ANALYSIS_MODE,
        "cache_mode": TASK_CACHE_MODE,
        "performance": analysis.performance,
        "cache_summary": scan.get("cache_summary"),
    }


def required_readiness_blockers(readiness: dict[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for gate in cast(list[Any], readiness.get("gates", [])):
        if not isinstance(gate, dict):
            continue
        typed_gate = cast(dict[str, Any], gate)
        if typed_gate.get("required") is True and typed_gate.get("state") != "certified":
            blockers.append(
                {
                    "code": "required_gate_not_ready",
                    "message": f"required gate {typed_gate.get('id')} is {typed_gate.get('state')}",
                }
            )
    return blockers


def finalize_task_check(
    *,
    repo_root: Path,
    config: dict[str, Any],
    run_dir: Path,
    task_id: str,
    run_id: str,
    baseline_run_id: str,
    check_mode: str,
    release_enforcement: str,
    snapshot: dict[str, Any],
    changed_paths: list[str],
    findings: dict[str, Any],
    delta: dict[str, Any],
    readiness: dict[str, Any],
    gate_results: list[dict[str, Any]],
    repository_blockers: list[dict[str, str]],
    contract_blockers: list[dict[str, str]],
    promotion_blockers: list[dict[str, str]],
    gate_blockers: list[dict[str, str]],
    readiness_blockers: list[dict[str, str]],
    analysis_evidence: dict[str, Any],
) -> dict[str, Any]:
    blockers = [
        *repository_blockers,
        *contract_blockers,
        *promotion_blockers,
        *delta.get("blockers", []),
        *gate_blockers,
        *readiness_blockers,
    ]
    failures = required_gate_failures(gate_results)
    decision = (
        "blocked"
        if blockers
        else "violation"
        if delta["counts"]["new_enforced"] or failures
        else "pass"
    )
    readiness_evidence = release_readiness(
        mode=check_mode,
        delta=delta,
        repository_blockers=repository_blockers,
        contract_blockers=contract_blockers,
        promotion_blockers=promotion_blockers,
        gate_blockers=gate_blockers,
        readiness_blockers=readiness_blockers,
        required_gate_failures=failures,
    )
    decision, blockers = enforce_release_eligibility(
        decision=decision,
        enforcement=release_enforcement,
        readiness=readiness_evidence,
        blockers=blockers,
    )
    payload = {
        "schema": TASK_CHECK_SCHEMA,
        "status": decision,
        "next_action": task_next_action(
            decision,
            mode=check_mode,
            enforcement=release_enforcement,
        ),
        "mode": check_mode,
        "release_enforcement": release_enforcement,
        "task_id": task_id,
        "run_id": run_id,
        "baseline_run_id": baseline_run_id,
        "repository": snapshot["repository"],
        "snapshot": snapshot,
        "changed_paths": changed_paths,
        "coverage": findings["coverage"],
        "normalized_findings": findings,
        "delta": delta,
        "prevention_readiness": readiness,
        "gate_results": gate_results,
        "required_gate_failures": failures,
        "blockers": deduplicate_blockers(blockers),
        "release_readiness": readiness_evidence,
        "analysis": analysis_evidence,
        "evidence": {
            **contract_hashes(repo_root, config),
            "toolchain_hash": readiness["toolchain_hash"],
            "task_analysis_mode": TASK_ANALYSIS_MODE,
            "task_cache_mode": TASK_CACHE_MODE,
        },
    }
    write_json(safe_child_file(run_dir, "workspace-snapshot.json"), snapshot)
    write_json(safe_child_file(run_dir, "normalized-findings.json"), findings)
    write_json(safe_child_file(run_dir, "prevention-readiness.json"), readiness)
    write_json(safe_child_file(run_dir, "task-check.json"), payload)
    write_text(safe_child_file(run_dir, "task-check.md"), render_task_check_markdown(payload))
    return payload
