from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from quality_runner.artifacts import (
    existing_artifact_dir,
    prepare_artifact_dir,
    write_json,
)
from quality_runner.schema_constants import DELIVERY_CONTRACT_SCHEMA


def run_artifacts(repo_root: Path, run_id: str) -> dict[str, Any]:
    directory = existing_artifact_dir(repo_root, run_id)
    values: dict[str, Any] = {}
    for name in (
        "repo-scan.json",
        "standards.json",
        "code-quality-scan.json",
        "security-scan.json",
        "remediation-plan.json",
        "performance.json",
    ):
        path = directory / name
        if not path.is_file() or path.is_symlink():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        values[name] = value
    return values


def current_qr_delta(repo_root: Path, run_id: str | None) -> dict[str, Any]:
    if not run_id:
        return {"run_id": None, "performance": None, "code_quality": None, "security": None}
    artifacts = run_artifacts(repo_root, run_id)
    return {
        "run_id": run_id,
        "performance": artifacts.get("performance.json"),
        "code_quality": summary(artifacts.get("code-quality-scan.json")),
        "security": summary(artifacts.get("security-scan.json")),
    }


def write_contract(repo_root: Path, run_id: str, contract: dict[str, Any]) -> Path:
    run_dir = prepare_artifact_dir(repo_root, run_id)
    return write_json(run_dir / "delivery-contract.json", contract)


def load_contract(path: Path) -> dict[str, Any]:
    value = load_json(path)
    if value.get("schema") != DELIVERY_CONTRACT_SCHEMA:
        raise ValueError(f"contract schema must be {DELIVERY_CONTRACT_SCHEMA}")
    return value


def load_result(path: Path | None) -> dict[str, Any]:
    if path is None:
        raise ValueError("reconcile requires --result-file or an inline result payload")
    return load_json(path)


def plan_text(path: Path | None, payload: dict[str, Any] | None) -> str:
    if payload is not None:
        return json.dumps(payload, sort_keys=True)
    if path is None:
        raise ValueError("preflight requires --plan-file")
    try:
        return path.expanduser().resolve().read_text(encoding="utf-8")
    except OSError as error:
        raise FileNotFoundError(f"plan file does not exist: {path}") from error


def obligation_covered(obligation: dict[str, Any], plan: str) -> bool:
    obligation_id = obligation.get("id")
    if isinstance(obligation_id, str) and obligation_id in plan:
        return True
    scope = obligation.get("scope")
    return (
        isinstance(scope, list)
        and bool(scope)
        and all(isinstance(path, str) and path in plan for path in scope)
    )


def deferred_checks(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return list_of_dicts(contract.get("deferred_checks"))


def obligations(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return list_of_dicts(contract.get("obligations"))


def source_fingerprints(
    repo_scan: dict[str, Any],
    code_quality: dict[str, Any],
    security: dict[str, Any],
) -> dict[str, str]:
    git = dict_value(repo_scan.get("git_provenance"))
    return {
        "git_head": str(git.get("head_sha") or "unknown"),
        "working_tree": value_hash(git),
        "code_quality_analysis": value_hash(dict_value(code_quality.get("analysis_cache"))),
        "security_analysis": value_hash(dict_value(security.get("analysis_cache"))),
    }


def git_baseline(repo_scan: dict[str, Any]) -> dict[str, Any]:
    git = dict_value(repo_scan.get("git_provenance"))
    return {
        "head_sha": git.get("head_sha"),
        "branch": git.get("branch"),
        "dirty": git.get("dirty"),
    }


def summary(value: object) -> dict[str, Any] | None:
    payload = dict_value(value)
    summary_value = payload.get("summary")
    return dict(summary_value) if isinstance(summary_value, dict) else None


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON artifact: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must contain an object: {path}")
    return cast(dict[str, Any], value)


def dict_value(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def list_of_dicts(value: object) -> list[dict[str, Any]]:
    return (
        [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    )


def string_list(value: object) -> list[str]:
    return (
        [item for item in value if isinstance(item, str) and item]
        if isinstance(value, list)
        else []
    )


def optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def value_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dedupe_blockers(blockers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for blocker in blockers:
        key = value_hash(blocker)
        if key in seen:
            continue
        seen.add(key)
        result.append(blocker)
    return result
