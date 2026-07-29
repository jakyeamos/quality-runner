from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from quality_runner.application.audit_workflows import run_payload
from quality_runner.artifacts import (
    existing_artifact_dir,
    write_json,
)
from quality_runner.delivery_contract_support import (
    current_qr_delta as _current_qr_delta,
)
from quality_runner.delivery_contract_support import (
    dedupe_blockers as _dedupe_blockers,
)
from quality_runner.delivery_contract_support import (
    deferred_checks as _deferred_checks,
)
from quality_runner.delivery_contract_support import (
    dict_value as _dict_value,
)
from quality_runner.delivery_contract_support import (
    git_baseline as _git_baseline,
)
from quality_runner.delivery_contract_support import (
    list_of_dicts as _list_of_dicts,
)
from quality_runner.delivery_contract_support import (
    load_contract as _load_contract,
)
from quality_runner.delivery_contract_support import (
    load_result as _load_result,
)
from quality_runner.delivery_contract_support import (
    obligation_covered as _obligation_covered,
)
from quality_runner.delivery_contract_support import (
    obligations as _obligations,
)
from quality_runner.delivery_contract_support import (
    optional_string as _optional_string,
)
from quality_runner.delivery_contract_support import (
    plan_text as _plan_text,
)
from quality_runner.delivery_contract_support import (
    run_artifacts as _run_artifacts,
)
from quality_runner.delivery_contract_support import (
    source_fingerprints as _source_fingerprints,
)
from quality_runner.delivery_contract_support import (
    string_list as _string_list,
)
from quality_runner.delivery_contract_support import (
    value_hash as _hash,
)
from quality_runner.delivery_contract_support import (
    write_contract as _write_contract,
)
from quality_runner.schema_constants import DELIVERY_CONTRACT_SCHEMA, DELIVERY_RESULT_SCHEMA
from quality_runner.workflow_internal import generated_run_id

ContractStage = Literal["prepare", "refresh"]


def prepare_delivery_contract(
    repo_root: Path,
    *,
    run_id: str | None = None,
    phase_id: str | None = None,
    plan_id: str | None = None,
    intent: str | None = None,
    analysis_mode: str = "balanced",
    cache_mode: str = "external",
    cache_root: Path | None = None,
    performance_budget_seconds: float | None = 30.0,
    context_refs: list[str] | None = None,
    research_refs: list[str] | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    resolved_run_id = run_id or generated_run_id(suffix="delivery-prepare")
    run_payload_result = _ensure_run(
        root,
        run_id=resolved_run_id,
        analysis_mode=analysis_mode,
        cache_mode=cache_mode,
        cache_root=cache_root,
        performance_budget_seconds=performance_budget_seconds,
        intent=intent,
    )
    contract = _build_contract(
        root,
        run_id=resolved_run_id,
        run_payload_result=run_payload_result,
        stage="prepare",
        phase_id=phase_id,
        plan_id=plan_id,
        intent=intent,
        analysis_mode=analysis_mode,
        cache_mode=cache_mode,
        performance_budget_seconds=performance_budget_seconds,
        context_refs=context_refs,
        research_refs=research_refs,
    )
    path = _write_contract(root, resolved_run_id, contract)
    return {**contract, "contract_path": str(path)}


def refresh_delivery_contract(
    repo_root: Path,
    *,
    contract_path: Path,
    run_id: str | None = None,
    phase_id: str | None = None,
    plan_id: str | None = None,
    intent: str | None = None,
    analysis_mode: str = "balanced",
    cache_mode: str = "external",
    cache_root: Path | None = None,
    performance_budget_seconds: float | None = 30.0,
    context_refs: list[str] | None = None,
    research_refs: list[str] | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    previous = _load_contract(contract_path)
    resolved_run_id = run_id or generated_run_id(suffix="delivery-refresh")
    inherited_phase = phase_id or _optional_string(previous.get("phase_id"))
    inherited_plan = plan_id or _optional_string(previous.get("plan_id"))
    inherited_intent = intent or _optional_string(previous.get("intent"))
    run_payload_result = _ensure_run(
        root,
        run_id=resolved_run_id,
        analysis_mode=analysis_mode,
        cache_mode=cache_mode,
        cache_root=cache_root,
        performance_budget_seconds=performance_budget_seconds,
        intent=inherited_intent,
    )
    contract = _build_contract(
        root,
        run_id=resolved_run_id,
        run_payload_result=run_payload_result,
        stage="refresh",
        phase_id=inherited_phase,
        plan_id=inherited_plan,
        intent=inherited_intent,
        analysis_mode=analysis_mode,
        cache_mode=cache_mode,
        performance_budget_seconds=performance_budget_seconds,
        context_refs=context_refs,
        research_refs=research_refs,
        parent_contract_id=_optional_string(previous.get("contract_id")),
    )
    path = _write_contract(root, resolved_run_id, contract)
    return {**contract, "contract_path": str(path)}


def preflight_delivery_contract(
    repo_root: Path,
    *,
    contract_path: Path,
    plan_path: Path | None = None,
    plan_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    contract = _load_contract(contract_path)
    plan_text = _plan_text(plan_path, plan_payload)
    obligations = _obligations(contract)
    coverage: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for obligation in obligations:
        obligation_id = str(obligation.get("id", "unknown"))
        hard = obligation.get("kind") == "hard"
        covered = _obligation_covered(obligation, plan_text)
        item = {
            "obligation_id": obligation_id,
            "kind": obligation.get("kind", "advisory"),
            "covered": covered,
            "evidence_required": obligation.get("required_evidence", []),
        }
        coverage.append(item)
        if hard and not covered:
            blockers.append(
                {
                    "type": "plan_coverage",
                    "obligation_id": obligation_id,
                    "message": "hard obligation is not represented in the native plan",
                }
            )
    for deferred in _deferred_checks(contract):
        if deferred.get("severity") == "hard":
            blockers.append(
                {
                    "type": "hard",
                    "check": deferred.get("check"),
                    "message": "hard check is deferred by the contract",
                }
            )
    status = "blocked" if blockers else "ready"
    return {
        "schema": DELIVERY_RESULT_SCHEMA,
        "operation": "preflight",
        "status": status,
        "implementation_allowed": False,
        "contract_id": contract.get("contract_id"),
        "contract_path": str(contract_path),
        "plan_path": str(plan_path) if plan_path is not None else None,
        "plan_scanned": False,
        "repository_scanned": False,
        "coverage": coverage,
        "blockers": blockers,
        "performance": contract.get("performance"),
    }


def reconcile_delivery_contract(
    repo_root: Path,
    *,
    contract_path: Path,
    result_path: Path | None = None,
    result_payload: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    root = repo_root.expanduser().resolve()
    contract = _load_contract(contract_path)
    execution = result_payload or _load_result(result_path)
    current_run_id = run_id or _optional_string(execution.get("qr_run_id"))
    blockers: list[dict[str, Any]] = []
    if execution.get("schema") not in {DELIVERY_RESULT_SCHEMA, None}:
        blockers.append({"type": "missing_evidence", "message": "execution result schema is invalid"})
    expected_fingerprints = _dict_value(contract.get("source_fingerprints"))
    actual_fingerprints = _dict_value(execution.get("source_fingerprints"))
    if not actual_fingerprints:
        blockers.append(
            {"type": "stale", "message": "execution result does not include source fingerprints"}
        )
    elif expected_fingerprints != actual_fingerprints:
        blockers.append(
            {
                "type": "stale",
                "message": "execution evidence was produced from a different source fingerprint",
                "expected": expected_fingerprints,
                "actual": actual_fingerprints,
            }
        )

    reported = {
        str(item.get("obligation_id")): item
        for item in execution.get("obligation_results", [])
        if isinstance(item, dict) and isinstance(item.get("obligation_id"), str)
    }
    obligation_results: list[dict[str, Any]] = []
    for obligation in _obligations(contract):
        obligation_id = str(obligation.get("id", "unknown"))
        item = reported.get(obligation_id)
        evidence_refs = item.get("evidence_refs") if isinstance(item, dict) else None
        status = item.get("status") if isinstance(item, dict) else "missing"
        has_evidence = isinstance(evidence_refs, list) and bool(
            [ref for ref in evidence_refs if isinstance(ref, str) and ref]
        )
        result_item = {
            "obligation_id": obligation_id,
            "kind": obligation.get("kind", "advisory"),
            "status": status,
            "evidence_refs": evidence_refs if isinstance(evidence_refs, list) else [],
            "verified": status in {"passed", "complete", "verified"} and has_evidence,
        }
        obligation_results.append(result_item)
        if obligation.get("kind") == "hard" and not result_item["verified"]:
            blockers.append(
                {
                    "type": "missing_evidence",
                    "obligation_id": obligation_id,
                    "message": "hard obligation lacks passing status and mandatory evidence",
                }
            )

    for deferred in _deferred_checks(contract):
        if deferred.get("severity") == "hard":
            blockers.append(
                {
                    "type": "hard",
                    "check": deferred.get("check"),
                    "message": "hard check remains deferred",
                }
            )

    current_delta = _current_qr_delta(root, current_run_id)
    status = "blocked" if blockers else "reconciled"
    result: dict[str, Any] = {
        "schema": DELIVERY_RESULT_SCHEMA,
        "operation": "reconcile",
        "status": status,
        "implementation_allowed": False,
        "contract_id": contract.get("contract_id"),
        "contract_path": str(contract_path),
        "qr_run_id": current_run_id,
        "obligation_results": obligation_results,
        "blockers": _dedupe_blockers(blockers),
        "current_qr_delta": current_delta,
        "performance": current_delta.get("performance"),
    }
    output_dir = (
        existing_artifact_dir(root, current_run_id)
        if current_run_id
        else contract_path.expanduser().resolve().parent
    )
    result["reconciliation_path"] = str(write_json(output_dir / "delivery-reconciliation.json", result))
    return result


def _ensure_run(
    repo_root: Path,
    *,
    run_id: str,
    analysis_mode: str,
    cache_mode: str,
    cache_root: Path | None,
    performance_budget_seconds: float | None,
    intent: str | None,
) -> dict[str, Any]:
    run_dir = repo_root / ".quality-runner" / "runs" / run_id
    if run_dir.is_dir() and (run_dir / "run-manifest.json").is_file():
        return {"run_id": run_id, "artifact_paths": {}}
    return run_payload(
        repo_root=repo_root,
        run_id=run_id,
        analysis_mode=analysis_mode,
        cache_mode=cache_mode,
        cache_root=cache_root,
        performance_budget_seconds=performance_budget_seconds,
        intent=(
            {"goal": intent, "source": "delivery-contract"}
            if isinstance(intent, str) and intent.strip()
            else None
        ),
    )


def _build_contract(
    repo_root: Path,
    *,
    run_id: str,
    run_payload_result: dict[str, Any],
    stage: ContractStage,
    phase_id: str | None,
    plan_id: str | None,
    intent: str | None,
    analysis_mode: str,
    cache_mode: str,
    performance_budget_seconds: float | None,
    context_refs: list[str] | None,
    research_refs: list[str] | None,
    parent_contract_id: str | None = None,
) -> dict[str, Any]:
    artifacts = _run_artifacts(repo_root, run_id)
    remediation_plan = _dict_value(artifacts.get("remediation-plan.json"))
    code_quality = _dict_value(artifacts.get("code-quality-scan.json"))
    security = _dict_value(artifacts.get("security-scan.json"))
    standards = _dict_value(artifacts.get("standards.json"))
    repo_scan = _dict_value(artifacts.get("repo-scan.json"))
    performance = _dict_value(artifacts.get("performance.json"))
    obligations = _build_obligations(remediation_plan, security)
    deferred_checks = _list_of_dicts(performance.get("deferred_checks"))
    source_fingerprints = _source_fingerprints(repo_scan, code_quality, security)
    now = datetime.now(UTC).isoformat()
    identity = {
        "stage": stage,
        "run_id": run_id,
        "parent_contract_id": parent_contract_id,
        "source_fingerprints": source_fingerprints,
        "obligations": obligations,
        "context_refs": sorted(context_refs or []),
        "research_refs": sorted(research_refs or []),
        "created_at": now,
    }
    contract_id = f"qrdc-{_hash(identity)[:16]}"
    return {
        "schema": DELIVERY_CONTRACT_SCHEMA,
        "contract_id": contract_id,
        "contract_stage": stage,
        "created_at": now,
        "repo_root": str(repo_root),
        "intent": intent,
        "phase_id": phase_id,
        "plan_id": plan_id,
        "qr_run_refs": [{"run_id": run_id, "artifact_paths": run_payload_result.get("artifact_paths", {})}],
        "git_baseline": _git_baseline(repo_scan),
        "source_fingerprints": source_fingerprints,
        "standards": {
            "profile": standards.get("profile"),
            "packet_schema": standards.get("schema"),
            "quality_skills": code_quality.get("quality_skills", []),
            "repo_instructions": repo_scan.get("agent_instruction_files", []),
            "truth_files": [repo_scan.get("truth_file")] if repo_scan.get("truth_file") else [],
            "qr_local_authority": True,
        },
        "context": {"refs": sorted(context_refs or []), "repo_scan": repo_scan.get("intent_docs", [])},
        "research": {"refs": sorted(research_refs or [])},
        "obligations": obligations,
        "analysis_mode": analysis_mode,
        "cache_mode": cache_mode,
        "latency_budget_seconds": performance_budget_seconds,
        "evidence_freshness": "current-run",
        "coverage": {
            "status": "partial" if deferred_checks else "complete",
            "hard_obligations": sum(1 for item in obligations if item.get("kind") == "hard"),
            "advisory_obligations": sum(1 for item in obligations if item.get("kind") == "advisory"),
        },
        "deferred_checks": deferred_checks,
        "performance": performance,
        "blockers": [],
        **({"parent_contract_id": parent_contract_id} if parent_contract_id else {}),
    }


def _build_obligations(remediation_plan: dict[str, Any], security: dict[str, Any]) -> list[dict[str, Any]]:
    obligations: list[dict[str, Any]] = []
    slices = remediation_plan.get("slices")
    if isinstance(slices, list):
        for item in slices:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            findings = item.get("findings")
            scope = sorted(
                {
                    str(finding.get("file"))
                    for finding in findings
                    if isinstance(finding, dict) and isinstance(finding.get("file"), str)
                }
                if isinstance(findings, list)
                else set()
            )
            acceptance = _string_list(item.get("verification_gates")) + _string_list(
                item.get("actions")
            )
            obligations.append(
                {
                    "id": f"slice:{item['id']}",
                    "title": item.get("title"),
                    "kind": "hard",
                    "scope": scope,
                    "acceptance_criteria": acceptance,
                    "required_evidence": _string_list(item.get("verification_gates")),
                    "verification_commands": _string_list(item.get("verification_gates")),
                    "stop_conditions": ["mandatory evidence is missing", "source fingerprint is stale"],
                }
            )
    for item in _list_of_dicts(security.get("agent_review_gates")):
        gate_id = item.get("id")
        if isinstance(gate_id, str):
            obligations.append(
                {
                    "id": f"security-review:{gate_id}",
                    "title": item.get("title", gate_id),
                    "kind": "advisory",
                    "scope": [],
                    "acceptance_criteria": _string_list(item.get("completion_criteria")),
                    "required_evidence": ["security review decision"],
                    "verification_commands": [],
                    "stop_conditions": [],
                }
            )
    return obligations
