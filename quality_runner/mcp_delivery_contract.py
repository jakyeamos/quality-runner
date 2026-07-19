from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.delivery_contract import (
    preflight_delivery_contract,
    prepare_delivery_contract,
    reconcile_delivery_contract,
    refresh_delivery_contract,
)


def delivery_contract_tool() -> dict[str, Any]:
    return {
        "name": "quality_runner_delivery_contract",
        "description": (
            "Prepare, refresh, preflight, or reconcile an additive QR delivery contract. "
            "Preflight consumes saved artifacts and does not rescan the repository."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_root": {"type": "string"},
                "operation": {
                    "type": "string",
                    "enum": ["prepare", "refresh", "preflight", "reconcile"],
                },
                "contract_path": {"type": "string"},
                "plan_file": {"type": "string"},
                "result_file": {"type": "string"},
                "run_id": {"type": "string"},
                "phase_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "intent": {"type": "string"},
                "analysis_mode": {"type": "string", "enum": ["balanced", "full"]},
                "cache_mode": {"type": "string", "enum": ["repo", "external", "disabled"]},
                "cache_dir": {"type": "string"},
                "performance_budget_seconds": {"type": "number", "minimum": 0},
                "context_refs": {"type": "array", "items": {"type": "string"}},
                "research_refs": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["repo_root", "operation"],
            "additionalProperties": False,
        },
    }


def delivery_contract_payload(arguments: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    operation = _required_string(arguments, "operation")
    cache_root = _path_arg(arguments, "cache_dir")
    context_refs = _string_list(arguments, "context_refs")
    research_refs = _string_list(arguments, "research_refs")
    if operation == "prepare":
        return prepare_delivery_contract(
            repo_root,
            run_id=_string_arg(arguments, "run_id"),
            phase_id=_string_arg(arguments, "phase_id"),
            plan_id=_string_arg(arguments, "plan_id"),
            intent=_string_arg(arguments, "intent"),
            analysis_mode=_string_arg(arguments, "analysis_mode") or "balanced",
            cache_mode=_string_arg(arguments, "cache_mode") or "external",
            cache_root=cache_root,
            performance_budget_seconds=_number_arg(arguments, "performance_budget_seconds", 30.0),
            context_refs=context_refs,
            research_refs=research_refs,
        )
    if operation == "refresh":
        return refresh_delivery_contract(
            repo_root,
            contract_path=_required_path_arg(arguments, "contract_path"),
            run_id=_string_arg(arguments, "run_id"),
            phase_id=_string_arg(arguments, "phase_id"),
            plan_id=_string_arg(arguments, "plan_id"),
            intent=_string_arg(arguments, "intent"),
            analysis_mode=_string_arg(arguments, "analysis_mode") or "balanced",
            cache_mode=_string_arg(arguments, "cache_mode") or "external",
            cache_root=cache_root,
            performance_budget_seconds=_number_arg(arguments, "performance_budget_seconds", 30.0),
            context_refs=context_refs,
            research_refs=research_refs,
        )
    if operation == "preflight":
        return preflight_delivery_contract(
            repo_root,
            contract_path=_required_path_arg(arguments, "contract_path"),
            plan_path=_required_path_arg(arguments, "plan_file"),
        )
    if operation == "reconcile":
        return reconcile_delivery_contract(
            repo_root,
            contract_path=_required_path_arg(arguments, "contract_path"),
            result_path=_required_path_arg(arguments, "result_file"),
            run_id=_string_arg(arguments, "run_id"),
        )
    raise ValueError("operation must be prepare, refresh, preflight, or reconcile")


def _string_arg(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_string(arguments: dict[str, Any], key: str) -> str:
    value = _string_arg(arguments, key)
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _path_arg(arguments: dict[str, Any], key: str) -> Path | None:
    value = _string_arg(arguments, key)
    return Path(value).expanduser().resolve() if value is not None else None


def _required_path_arg(arguments: dict[str, Any], key: str) -> Path:
    value = _path_arg(arguments, key)
    if value is None:
        raise ValueError(f"{key} is required")
    return value


def _string_list(arguments: dict[str, Any], key: str) -> list[str]:
    value = arguments.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{key} must be an array of strings")
    return list(value)


def _number_arg(arguments: dict[str, Any], key: str, default: float) -> float:
    value = arguments.get(key, default)
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative number")
    return float(value)
