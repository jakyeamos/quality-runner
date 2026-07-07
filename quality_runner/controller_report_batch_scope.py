from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast


def load_batch_scope_file(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"batch scope file does not exist: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("batch scope JSON must contain an object")
    return normalize_batch_scope(payload)


def normalize_batch_scope(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, Any] = {}
    for field in ("cluster_id", "intent_ref"):
        item = value.get(field)
        if isinstance(item, str) and item:
            normalized[field] = item
    for field in ("finding_ids", "fingerprint_prefixes", "allowed_files"):
        items = value.get(field)
        if _string_list(items):
            normalized[field] = sorted(set(cast(list[str], items)))
    return normalized


def evaluate_batch_scope(
    *,
    batch_scope: dict[str, Any],
    files_changed: list[str],
) -> dict[str, Any]:
    allowed = batch_scope.get("allowed_files")
    if not _string_list(allowed):
        return {
            "unrelated_files_changed": [],
            "scope_violation": False,
        }
    allowed_set = {item.replace("\\", "/").lstrip("./") for item in cast(list[str], allowed)}
    unrelated = sorted(
        {
            path
            for path in files_changed
            if not _path_allowed(path.replace("\\", "/").lstrip("./"), allowed_set)
        }
    )
    return {
        "unrelated_files_changed": unrelated,
        "scope_violation": bool(unrelated),
    }


def batch_scope_strict_errors(
    *,
    batch_scope: dict[str, Any],
    files_changed: list[str],
) -> list[str]:
    evaluation = evaluate_batch_scope(batch_scope=batch_scope, files_changed=files_changed)
    errors: list[str] = []
    if evaluation["scope_violation"]:
        unrelated = evaluation["unrelated_files_changed"]
        errors.append(
            "controller report files_changed includes paths outside batch_scope.allowed_files: "
            + ", ".join(unrelated)
        )
    finding_ids = batch_scope.get("finding_ids")
    if (
        _string_list(finding_ids)
        and files_changed
        and not _string_list(batch_scope.get("allowed_files"))
    ):
        errors.append(
            "batch_scope provides finding_ids without allowed_files; "
            "strict lint cannot attest file scope"
        )
    return errors


def _path_allowed(path: str, allowed_paths: set[str]) -> bool:
    return any(path == allowed or path.startswith(f"{allowed}/") for allowed in allowed_paths)


def _string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)
