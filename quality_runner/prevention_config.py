from __future__ import annotations

from typing import Any

RULE_STATES = {
    "candidate",
    "reviewed",
    "projected",
    "trigger-verified",
    "behavior-verified",
}
GATE_STATES = {"candidate", "certified"}


def parse_prevention_section(
    value: object,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(_warning("quality_runner.prevention must be a table"))
        return {}

    required_modules = _string_list(
        value.get("required_modules"),
        "quality_runner.prevention.required_modules",
        warnings,
    )
    environment_paths = _string_list(
        value.get("environment_paths"),
        "quality_runner.prevention.environment_paths",
        warnings,
    )
    snapshot_include_paths = _string_list(
        value.get("snapshot_include_paths"),
        "quality_runner.prevention.snapshot_include_paths",
        warnings,
    )
    rules = _rules(value.get("rules"), warnings)
    gates = _gates(value.get("gates"), warnings)
    return {
        "required_modules": required_modules,
        "environment_paths": environment_paths,
        "snapshot_include_paths": snapshot_include_paths,
        "rules": rules,
        "gates": gates,
    }


def _rules(value: object, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(_warning("quality_runner.prevention.rules must be an array of tables"))
        return []

    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        field = f"quality_runner.prevention.rules[{index}]"
        if not isinstance(item, dict):
            warnings.append(_warning(f"{field} must be a table"))
            continue
        required = _required_strings(
            item,
            ("detector", "rule_id", "state", "owner", "rationale"),
            field,
            warnings,
        )
        if required is None:
            continue
        state = required["state"]
        if state not in RULE_STATES:
            warnings.append(
                _warning(f"{field}.state must be one of {', '.join(sorted(RULE_STATES))}")
            )
            continue
        evidence_refs = _string_list(item.get("evidence_refs"), f"{field}.evidence_refs", warnings)
        paths = _string_list(item.get("paths"), f"{field}.paths", warnings)
        confidence = item.get("confidence_threshold", 0.0)
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            warnings.append(_warning(f"{field}.confidence_threshold must be a number"))
            continue
        result.append(
            {
                **required,
                "evidence_refs": evidence_refs,
                "paths": paths,
                "confidence_threshold": float(confidence),
            }
        )
    return result


def _gates(value: object, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(_warning("quality_runner.prevention.gates must be an array of tables"))
        return []

    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        field = f"quality_runner.prevention.gates[{index}]"
        if not isinstance(item, dict):
            warnings.append(_warning(f"{field} must be a table"))
            continue
        required = _required_strings(
            item,
            ("id", "command", "state", "owner", "rationale", "bootstrap", "mutation_risk"),
            field,
            warnings,
        )
        if required is None:
            continue
        state = required["state"]
        if state not in GATE_STATES:
            warnings.append(
                _warning(f"{field}.state must be one of {', '.join(sorted(GATE_STATES))}")
            )
            continue
        timeout = item.get("timeout_seconds", 120)
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            warnings.append(_warning(f"{field}.timeout_seconds must be a positive integer"))
            continue
        required_gate = item.get("required", False)
        if not isinstance(required_gate, bool):
            warnings.append(_warning(f"{field}.required must be a boolean"))
            continue
        result.append(
            {
                **required,
                "required": required_gate,
                "timeout_seconds": timeout,
                "scope": _optional_string(item.get("scope"), f"{field}.scope", warnings),
                "evidence_refs": _string_list(
                    item.get("evidence_refs"), f"{field}.evidence_refs", warnings
                ),
                "environment_paths": _string_list(
                    item.get("environment_paths"), f"{field}.environment_paths", warnings
                ),
            }
        )
    return result


def _required_strings(
    item: dict[str, object],
    names: tuple[str, ...],
    field: str,
    warnings: list[dict[str, str]],
) -> dict[str, str] | None:
    result: dict[str, str] = {}
    valid = True
    for name in names:
        value = item.get(name)
        if not isinstance(value, str) or not value.strip():
            warnings.append(_warning(f"{field}.{name} must be a non-empty string"))
            valid = False
        else:
            result[name] = value.strip()
    return result if valid else None


def _string_list(
    value: object,
    field: str,
    warnings: list[dict[str, str]],
) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return list(value)
    warnings.append(_warning(f"{field} must be a list of non-empty strings"))
    return []


def _optional_string(
    value: object,
    field: str,
    warnings: list[dict[str, str]],
) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    warnings.append(_warning(f"{field} must be a non-empty string"))
    return None


def _warning(message: str) -> dict[str, str]:
    return {
        "code": "invalid_quality_runner_config_field",
        "message": message,
    }
