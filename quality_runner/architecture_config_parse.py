from __future__ import annotations

from typing import Any

CONFIG_FILE_NAME = ".quality-runner.toml"


def parse_architecture_section(
    value: object,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(_warning("quality_runner.architecture must be a table"))
        return {}

    result: dict[str, Any] = {}
    enabled = value.get("enabled")
    if enabled is not None:
        if isinstance(enabled, bool):
            result["enabled"] = enabled
        else:
            warnings.append(_warning("quality_runner.architecture.enabled must be a boolean"))

    import_boundaries = _import_boundaries(value.get("import_boundaries"), warnings)
    if import_boundaries:
        result["import_boundaries"] = import_boundaries

    pattern_boundaries = _pattern_boundaries(value.get("pattern_boundaries"), warnings)
    if pattern_boundaries:
        result["pattern_boundaries"] = pattern_boundaries

    return result


def _import_boundaries(value: object, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(_warning("quality_runner.architecture.import_boundaries must be a list"))
        return []

    rules: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rule_id = _non_empty_string(item.get("id"))
        sources = _string_list(item.get("sources"))
        disallowed = _string_list(item.get("disallowed_imports"))
        if not rule_id or not sources or not disallowed:
            continue
        rule: dict[str, Any] = {
            "id": rule_id,
            "sources": sources,
            "disallowed_imports": disallowed,
            "allowed_imports": _string_list(item.get("allowed_imports")),
        }
        severity = _non_empty_string(item.get("severity"))
        if severity in {"warning", "observation"}:
            rule["severity"] = severity
        message = _non_empty_string(item.get("message"))
        if message:
            rule["message"] = message
        risk = _non_empty_string(item.get("risk"))
        if risk:
            rule["risk"] = risk
        expected = _non_empty_string(item.get("expected"))
        if expected:
            rule["expected"] = expected
        rules.append(rule)
    return rules


def _pattern_boundaries(value: object, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(_warning("quality_runner.architecture.pattern_boundaries must be a list"))
        return []

    rules: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rule_id = _non_empty_string(item.get("id"))
        paths = _string_list(item.get("paths"))
        patterns = _string_list(item.get("disallowed_patterns"))
        if not rule_id or not paths or not patterns:
            continue
        compiled: list[str] = []
        for pattern in patterns:
            compiled.append(pattern)
        rule: dict[str, Any] = {
            "id": rule_id,
            "paths": paths,
            "disallowed_patterns": compiled,
        }
        severity = _non_empty_string(item.get("severity"))
        if severity in {"warning", "observation"}:
            rule["severity"] = severity
        message = _non_empty_string(item.get("message"))
        if message:
            rule["message"] = message
        risk = _non_empty_string(item.get("risk"))
        if risk:
            rule["risk"] = risk
        expected = _non_empty_string(item.get("expected"))
        if expected:
            rule["expected"] = expected
        rules.append(rule)
    return rules


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _non_empty_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _warning(message: str) -> dict[str, str]:
    return {
        "code": "invalid_quality_runner_config_field",
        "message": message,
        "path": CONFIG_FILE_NAME,
    }
