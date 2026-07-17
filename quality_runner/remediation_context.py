from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, cast

from quality_runner.schema_constants import REMEDIATION_CONTEXT_SCHEMA

_CONTEXT_STATUSES = {"needs-understanding", "ready"}
_RISK_TIERS = {"local", "cross-layer", "high-risk"}
_BASE_AGENT_FIELDS = (
    "behavior_invariants",
    "non_goals",
    "known_unknowns",
    "characterization_evidence",
)
_HIGH_RISK_DOMAINS = {
    "data-integrity",
    "publication-visibility",
    "release-readiness",
}
_CROSS_LAYER_DOMAINS = {
    "architecture-maintainability",
    "integration-decisions",
    "performance",
    "testing-quality",
    "ui-quality",
}
_HIGH_RISK_PATH_MARKERS = (
    ".github/workflows/",
    "/api/",
    "app/api/",
    "auth",
    "inngest",
    "middleware",
    "migrations/",
    "rollback",
    "storage",
    "webhook",
)


def build_remediation_context(
    *,
    run_id: str | None,
    repo_root: Path | None,
    slices: list[dict[str, Any]],
    security_review_slices: list[dict[str, Any]] | None = None,
    repo_scan: dict[str, Any] | None = None,
    git_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    all_slices = [*slices, *(security_review_slices or [])]
    repo_context = _repo_context(repo_scan)
    records = [
        _build_record(
            slice_item,
            repo_context=repo_context,
            git_state=git_state,
        )
        for slice_item in all_slices
        if isinstance(slice_item, dict)
    ]
    finding_ids = {finding_id for record in records for finding_id in record["finding_ids"]}
    risk_counts = Counter(str(record["risk_tier"]) for record in records)
    ready_count = sum(record["status"] == "ready" for record in records)
    pending_count = len(records) - ready_count
    summary = {
        "status": "needs-understanding" if pending_count else "ready",
        "blocking": pending_count > 0,
        "record_count": len(records),
        "finding_count": len(finding_ids),
        "ready_count": ready_count,
        "pending_count": pending_count,
        "by_risk_tier": dict(sorted(risk_counts.items())),
    }
    return {
        "schema": REMEDIATION_CONTEXT_SCHEMA,
        "run_id": run_id,
        "repo_root": str(repo_root.expanduser().resolve()) if repo_root is not None else None,
        "policy": {
            "scope_unit": "bounded-remediation-slice",
            "raw_findings_are_grouped": True,
            "per_finding_documentation_required": False,
            "agent_completion_requires": list(_BASE_AGENT_FIELDS),
            "high_risk_additions": ["impact_map", "affected_boundaries", "verification_baseline"],
        },
        "repo_context": repo_context,
        "records": records,
        "summary": summary,
    }


def attach_context_refs(
    slices: list[dict[str, Any]],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    records = context.get("records")
    by_slice_id: dict[str, dict[str, Any]] = {}
    if isinstance(records, list):
        by_slice_id = {
            str(record["slice_id"]): record
            for record in records
            if isinstance(record, dict) and isinstance(record.get("slice_id"), str)
        }
    enriched: list[dict[str, Any]] = []
    for slice_item in slices:
        item = dict(slice_item)
        record = by_slice_id.get(str(item.get("id") or ""))
        if record is not None:
            item["context_id"] = record["context_id"]
            item["context_status"] = record["status"]
            item["context_requirements"] = list(record["required_agent_fields"])
        enriched.append(item)
    return enriched


def remediation_context_summary(
    context: dict[str, Any] | None,
    *,
    artifact_path: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(context, dict):
        return None
    summary = context.get("summary")
    if not isinstance(summary, dict) and "status" in context:
        summary = context
    if not isinstance(summary, dict):
        return None

    def _count(name: str) -> int:
        value = summary.get(name)
        return value if isinstance(value, int) and value >= 0 else 0

    result: dict[str, Any] = {
        "schema": context.get("schema", REMEDIATION_CONTEXT_SCHEMA),
        "status": summary.get("status", "needs-understanding"),
        "blocking": bool(summary.get("blocking", True)),
        "record_count": _count("record_count"),
        "finding_count": _count("finding_count"),
        "ready_count": _count("ready_count"),
        "pending_count": _count("pending_count"),
    }
    if isinstance(artifact_path, str) and artifact_path:
        result["artifact_path"] = artifact_path
    return result


def build_remediation_context_for_plan(
    *,
    remediation_plan: dict[str, Any],
    run_id: str | None,
    repo_root: Path | None,
    repo_scan: dict[str, Any] | None = None,
    git_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slices: list[dict[str, Any]] = []
    for collection_name in ("slices", "security_review_slices"):
        collection = remediation_plan.get(collection_name)
        if isinstance(collection, list):
            slices.extend(item for item in collection if isinstance(item, dict))
    return build_remediation_context(
        run_id=run_id,
        repo_root=repo_root,
        slices=slices,
        repo_scan=repo_scan,
        git_state=git_state,
    )


def validate_remediation_context(
    context: dict[str, Any],
    *,
    remediation_plan: dict[str, Any] | None = None,
    require_ready: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    if context.get("schema") != REMEDIATION_CONTEXT_SCHEMA:
        errors.append(f"remediation context schema must be {REMEDIATION_CONTEXT_SCHEMA}")
    records = context.get("records")
    if not isinstance(records, list):
        errors.append("remediation context records must be a list")
        return {"passed": False, "errors": errors, "readiness": _empty_readiness()}

    expected_slice_ids = _plan_slice_ids(remediation_plan)
    seen_slice_ids: set[str] = set()
    seen_context_ids: set[str] = set()
    ready_count = 0
    pending_count = 0
    finding_ids: set[str] = set()
    risk_counts: Counter[str] = Counter()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"remediation context record at index {index} is not an object")
            continue
        record_errors = _validate_record(record, index=index)
        errors.extend(record_errors)
        slice_id = record.get("slice_id")
        context_id = record.get("context_id")
        if isinstance(slice_id, str):
            if slice_id in seen_slice_ids:
                errors.append(f"remediation context duplicates slice {slice_id}")
            seen_slice_ids.add(slice_id)
            if expected_slice_ids and slice_id not in expected_slice_ids:
                errors.append(f"remediation context references unknown slice {slice_id}")
        if isinstance(context_id, str):
            if context_id in seen_context_ids:
                errors.append(f"remediation context duplicates context {context_id}")
            seen_context_ids.add(context_id)
        ids = record.get("finding_ids")
        if isinstance(ids, list):
            finding_ids.update(item for item in ids if isinstance(item, str))
        risk_tier = record.get("risk_tier")
        if isinstance(risk_tier, str):
            risk_counts[risk_tier] += 1
        if record.get("status") == "ready":
            ready_count += 1
        else:
            pending_count += 1
            if require_ready and isinstance(slice_id, str):
                errors.append(f"remediation context for slice {slice_id} is not ready")

    if expected_slice_ids:
        missing = sorted(expected_slice_ids - seen_slice_ids)
        errors.extend(f"remediation context missing slice {slice_id}" for slice_id in missing)
    readiness = {
        "status": "needs-understanding" if pending_count else "ready",
        "blocking": pending_count > 0,
        "record_count": len(records),
        "finding_count": len(finding_ids),
        "ready_count": ready_count,
        "pending_count": pending_count,
        "by_risk_tier": dict(sorted(risk_counts.items())),
    }
    declared_summary = context.get("summary")
    if isinstance(declared_summary, dict):
        for field in (
            "status",
            "blocking",
            "record_count",
            "finding_count",
            "ready_count",
            "pending_count",
            "by_risk_tier",
        ):
            if declared_summary.get(field) != readiness[field]:
                errors.append(f"remediation context summary field {field} is stale")
    return {"passed": not errors, "errors": errors, "readiness": readiness}


def _build_record(
    slice_item: dict[str, Any],
    *,
    repo_context: dict[str, Any],
    git_state: dict[str, Any] | None,
) -> dict[str, Any]:
    slice_id = str(slice_item.get("id") or "unknown-slice")
    findings = [finding for finding in slice_item.get("findings", []) if isinstance(finding, dict)]
    files = sorted(
        {
            str(finding["file"])
            for finding in findings
            if isinstance(finding.get("file"), str) and finding["file"]
        }
    )
    categories = sorted(
        {
            str(finding["category"])
            for finding in findings
            if isinstance(finding.get("category"), str) and finding["category"]
        }
    )
    rule_ids = sorted(
        {
            str(finding["rule_id"])
            for finding in findings
            if isinstance(finding.get("rule_id"), str) and finding["rule_id"]
        }
    )
    finding_ids = sorted(
        {
            str(finding["id"])
            for finding in findings
            if isinstance(finding.get("id"), str) and finding["id"]
        }
    )
    risk_tier = _risk_tier(slice_item, categories=categories, files=files)
    required_fields: list[str] = list(_BASE_AGENT_FIELDS)
    if risk_tier in {"cross-layer", "high-risk"}:
        required_fields.append("impact_map")
    if risk_tier == "high-risk":
        required_fields.extend(["affected_boundaries", "verification_baseline"])
    boundaries = _boundaries(slice_item, files=files)
    anchors = [_finding_anchor(finding) for finding in findings]
    anchors = [anchor for anchor in anchors if anchor is not None]
    machine_evidence: dict[str, Any] = {
        "scope_paths": files,
        "finding_anchors": anchors,
        "intent_docs": list(repo_context.get("intent_docs", [])),
    }
    planned_git = _planned_git(git_state)
    if planned_git is not None:
        machine_evidence["planned_git"] = planned_git
    drift_check = slice_item.get("drift_check")
    if isinstance(drift_check, dict):
        machine_evidence["drift_check"] = drift_check
    verification: dict[str, Any] = {
        "mode": slice_item.get("verification_mode", "command"),
        "commands": _string_list(slice_item.get("verification_gates")),
    }
    requirements = _string_list(slice_item.get("verification_requirements"))
    if requirements:
        verification["requirements"] = requirements
    return {
        "context_id": f"context-{slice_id}",
        "slice_id": slice_id,
        "status": "needs-understanding",
        "risk_tier": risk_tier,
        "domain": str(slice_item.get("domain") or "general-quality"),
        "workstream": str(slice_item.get("workstream") or "unclassified"),
        "finding_ids": finding_ids,
        "files": files,
        "categories": categories,
        "rule_ids": rule_ids,
        "boundaries": boundaries,
        "required_agent_fields": required_fields,
        "agent_evidence": {field: [] for field in _all_agent_fields()},
        "machine_evidence": machine_evidence,
        "verification": verification,
    }


def _validate_record(record: dict[str, Any], *, index: int) -> list[str]:
    errors: list[str] = []
    label = str(record.get("slice_id") or f"at index {index}")
    for field in ("context_id", "slice_id", "status", "risk_tier", "domain", "workstream"):
        if not isinstance(record.get(field), str) or not record[field]:
            errors.append(
                f"remediation context record {label} field {field} must be a non-empty string"
            )
    if record.get("status") not in _CONTEXT_STATUSES:
        errors.append(f"remediation context record {label} status is invalid")
    if record.get("risk_tier") not in _RISK_TIERS:
        errors.append(f"remediation context record {label} risk_tier is invalid")
    for field in ("finding_ids", "categories", "boundaries", "required_agent_fields"):
        if not _is_string_list(record.get(field), allow_empty=False):
            errors.append(f"remediation context record {label} field {field} must be a string list")
    for field in ("files", "rule_ids"):
        if not _is_string_list(record.get(field), allow_empty=True):
            errors.append(f"remediation context record {label} field {field} must be a string list")
    machine_evidence = record.get("machine_evidence")
    if not isinstance(machine_evidence, dict):
        errors.append(f"remediation context record {label} machine_evidence must be an object")
    agent_evidence = record.get("agent_evidence")
    if not isinstance(agent_evidence, dict):
        errors.append(f"remediation context record {label} agent_evidence must be an object")
    else:
        for field in _all_agent_fields():
            if not _is_string_list(agent_evidence.get(field), allow_empty=True):
                errors.append(
                    f"remediation context record {label} agent_evidence.{field} must be a string list"
                )
        required = record.get("required_agent_fields")
        if isinstance(required, list) and record.get("status") == "ready":
            for field in required:
                if isinstance(field, str) and not agent_evidence.get(field):
                    errors.append(f"remediation context for slice {label} is ready without {field}")
    verification = record.get("verification")
    if not isinstance(verification, dict) or not _is_string_list(
        verification.get("commands"), allow_empty=True
    ):
        errors.append(f"remediation context record {label} verification is incomplete")
    return errors


def _risk_tier(slice_item: dict[str, Any], *, categories: list[str], files: list[str]) -> str:
    domain = str(slice_item.get("domain") or "")
    lowered_files = [file.lower() for file in files]
    if (
        domain in _HIGH_RISK_DOMAINS
        or any(category.startswith("security:") for category in categories)
        or any(marker in file for file in lowered_files for marker in _HIGH_RISK_PATH_MARKERS)
    ):
        return "high-risk"
    if domain in _CROSS_LAYER_DOMAINS or len(files) > 1:
        return "cross-layer"
    return "local"


def _boundaries(slice_item: dict[str, Any], *, files: list[str]) -> list[str]:
    values = {
        str(slice_item.get("domain") or "general-quality"),
        str(slice_item.get("workstream") or "unclassified"),
    }
    lowered_files = [file.lower() for file in files]
    boundary_markers = {
        "api": ("/api/", "app/api/"),
        "auth": ("auth", "middleware", "proxy"),
        "database": ("migrations/", "rollback", ".sql"),
        "workflow": (".github/workflows/", "inngest"),
        "tests": ("test", "__tests__", "e2e"),
        "storage": ("storage", "upload", "media"),
    }
    for boundary, markers in boundary_markers.items():
        if any(marker in file for file in lowered_files for marker in markers):
            values.add(boundary)
    return sorted(values)


def _finding_anchor(finding: dict[str, Any]) -> dict[str, Any] | None:
    finding_id = finding.get("id")
    if not isinstance(finding_id, str) or not finding_id:
        return None
    anchor: dict[str, Any] = {"finding_id": finding_id}
    for field in ("file", "line", "rule_id", "fingerprint"):
        value = finding.get(field)
        if (isinstance(value, str) and value) or (isinstance(value, int) and value > 0):
            anchor[field] = value
    return anchor


def _repo_context(repo_scan: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(repo_scan, dict):
        return {}
    result: dict[str, Any] = {}
    for key in ("package_manager", "languages"):
        value = repo_scan.get(key)
        if isinstance(value, str) and value:
            result[key] = value
        elif isinstance(value, list) and all(isinstance(item, str) and item for item in value):
            result[key] = list(value)
    intent_docs = repo_scan.get("intent_docs")
    if isinstance(intent_docs, list):
        paths = [
            item["path"]
            for item in intent_docs
            if isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"]
        ]
        if paths:
            result["intent_docs"] = sorted(set(paths))
    return result


def _planned_git(git_state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(git_state, dict):
        return None
    result = {
        key: git_state[key]
        for key in ("head_sha", "branch", "dirty")
        if git_state.get(key) is not None
    }
    return result or None


def _plan_slice_ids(remediation_plan: dict[str, Any] | None) -> set[str]:
    if not isinstance(remediation_plan, dict):
        return set()
    ids: set[str] = set()
    for collection_name in ("slices", "security_review_slices"):
        collection = remediation_plan.get(collection_name)
        if not isinstance(collection, list):
            continue
        ids.update(
            str(item["id"])
            for item in collection
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]
        )
    return ids


def _all_agent_fields() -> tuple[str, ...]:
    return (*_BASE_AGENT_FIELDS, "impact_map", "affected_boundaries", "verification_baseline")


def _string_list(value: object) -> list[str]:
    if not _is_string_list(value, allow_empty=True):
        return []
    return list(cast(list[str], value))


def _is_string_list(value: object, *, allow_empty: bool) -> bool:
    return (
        isinstance(value, list)
        and (allow_empty or bool(value))
        and all(isinstance(item, str) and item for item in value)
    )


def _empty_readiness() -> dict[str, Any]:
    return {
        "status": "needs-understanding",
        "blocking": True,
        "record_count": 0,
        "finding_count": 0,
        "ready_count": 0,
        "pending_count": 0,
        "by_risk_tier": {},
    }
