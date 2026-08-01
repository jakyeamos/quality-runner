from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PHASE_CONTRACT_SCHEMA = "quality-runner-phase-contract-v0.1"
SCAN_TIERS = {"targeted", "phase", "repo"}
ACCEPTED_DISPOSITIONS = {"accepted-false-positive", "accepted-intentional"}
BLOCKING_DISPOSITIONS = {
    "blocked",
    "blocked-with-prerequisite",
    "review-required",
    "unresolved",
    "unreviewed",
    "accepted-risk",
    "true-positive",
}


def load_phase_contract(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"phase contract must be a regular file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("phase contract must contain a JSON object")
    validate_phase_contract(payload)
    return payload


def validate_phase_contract(contract: dict[str, Any]) -> None:
    if contract.get("schema") != PHASE_CONTRACT_SCHEMA:
        raise ValueError(f"phase contract schema must be {PHASE_CONTRACT_SCHEMA}")
    phase_id = contract.get("phase_id")
    if not isinstance(phase_id, str) or not phase_id.strip():
        raise ValueError("phase contract requires phase_id")
    tier = contract.get("scan_tier", "phase")
    if tier not in SCAN_TIERS:
        raise ValueError(f"scan_tier must be one of {sorted(SCAN_TIERS)}")
    scope = contract.get("scope", {})
    if not isinstance(scope, dict):
        raise ValueError("phase contract scope must be an object")
    for field in ("include_paths", "exclude_paths", "rules", "categories"):
        value = scope.get(field, [])
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise ValueError(f"phase contract scope.{field} must be a list of strings")
    if tier in {"targeted", "phase"} and not scope.get("include_paths"):
        raise ValueError("targeted and phase scans require scope.include_paths")
    for item in contract.get("finding_map", []):
        if not isinstance(item, dict) or not item.get("fingerprints"):
            raise ValueError("finding_map entries require fingerprints")
        if not isinstance(item.get("fingerprints"), list):
            raise ValueError("finding_map fingerprints must be a list")
    for item in contract.get("dispositions", []):
        if not isinstance(item, dict):
            raise ValueError("dispositions must contain objects")
        status = item.get("status")
        if status not in ACCEPTED_DISPOSITIONS:
            raise ValueError(f"unsupported accepted disposition: {status}")
        for field in ("fingerprint", "reason", "owner", "evidence"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"accepted disposition requires {field}")


def scan_include_paths(contract: dict[str, Any]) -> tuple[str, ...]:
    validate_phase_contract(contract)
    if contract.get("scan_tier") == "repo":
        return ()
    scope = contract.get("scope")
    return tuple(scope.get("include_paths", [])) if isinstance(scope, dict) else ()


def path_in_scope(path: str, contract: dict[str, Any]) -> bool:
    scope = contract.get("scope")
    if not isinstance(scope, dict):
        return False
    normalized = path.replace("\\", "/").strip("/")
    excluded = _normalized_paths(scope.get("exclude_paths"))
    if any(normalized == item or normalized.startswith(f"{item}/") for item in excluded):
        return False
    included = _normalized_paths(scope.get("include_paths"))
    if not included:
        return True
    return any(normalized == item or normalized.startswith(f"{item}/") for item in included)


def finding_matches_contract(finding: dict[str, Any], contract: dict[str, Any]) -> bool:
    path = finding.get("file") or finding.get("path") or finding.get("location")
    if not isinstance(path, str) or not path_in_scope(path.split(":", 1)[0], contract):
        return False
    scope = contract.get("scope")
    if not isinstance(scope, dict):
        return False
    rule = finding.get("rule_id") or finding.get("rule")
    rules = scope.get("rules", [])
    if rules and rule not in rules:
        return False
    category = finding.get("category")
    categories = scope.get("categories", [])
    return not categories or category in categories


def finding_owner(fingerprint: str, contract: dict[str, Any]) -> dict[str, Any]:
    for item in contract.get("finding_map", []):
        if isinstance(item, dict) and fingerprint in item.get("fingerprints", []):
            return {
                "mapped": True,
                "phase_id": contract["phase_id"],
                "plan_id": item.get("plan_id") or contract.get("plan_id"),
                "task_id": item.get("task_id"),
            }
    return {
        "mapped": False,
        "phase_id": contract["phase_id"],
        "plan_id": contract.get("plan_id"),
        "task_id": None,
    }


def early_refresh_recommendation(
    contract: dict[str, Any], changed_paths: list[str] | None = None
) -> dict[str, Any]:
    paths = [item.replace("\\", "/").strip("/") for item in changed_paths or []]
    out_of_scope = [path for path in paths if not path_in_scope(path, contract)]
    security_paths = [
        path
        for path in paths
        if any(
            marker in f"/{path.lower()}" for marker in ("/auth", "/security", "/webhook", "/api/")
        )
    ]
    reasons = [
        *(["changed path is outside the declared phase scope"] if out_of_scope else []),
        *(["security-sensitive path changed"] if security_paths else []),
    ]
    if paths:
        reasons.extend(
            item for item in contract.get("early_refresh_triggers", []) if isinstance(item, str)
        )
    return {
        "recommended": bool(reasons),
        "reasons": sorted(set(reasons)),
        "out_of_scope_paths": sorted(set(out_of_scope)),
        "security_sensitive_paths": sorted(set(security_paths)),
    }


def _normalized_paths(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        item.replace("\\", "/").strip("/") for item in value if isinstance(item, str) and item
    )
