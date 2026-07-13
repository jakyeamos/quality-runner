from __future__ import annotations

import re
from typing import Any


def parse_artifacts_section(value: object, warnings: list[dict[str, str]]) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(
            _warning(
                "invalid_quality_runner_config_field",
                "quality_runner.artifacts must be a table",
            )
        )
        return {}

    patterns = _string_list(
        value.get("redact_patterns"),
        "quality_runner.artifacts.redact_patterns",
        warnings,
    )
    valid_patterns: list[str] = []
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error:
            warnings.append(
                _warning(
                    "invalid_quality_runner_config_field",
                    "quality_runner.artifacts.redact_patterns must contain valid regular expressions",
                )
            )
            continue
        valid_patterns.append(pattern)
    replacement = _string_value(
        value.get("redact_replacement"),
        "quality_runner.artifacts.redact_replacement",
        warnings,
    )
    retention_runs = _positive_int(
        value.get("retention_runs"), "quality_runner.artifacts.retention_runs", warnings
    )
    retention_days = _positive_int(
        value.get("retention_days"), "quality_runner.artifacts.retention_days", warnings
    )

    parsed: dict[str, Any] = {}
    if valid_patterns:
        parsed["redact_patterns"] = valid_patterns
    if replacement is not None:
        parsed["redact_replacement"] = replacement
    if retention_runs is not None:
        parsed["retention_runs"] = retention_runs
    if retention_days is not None:
        parsed["retention_days"] = retention_days
    return parsed


def _positive_int(value: object, field: str, warnings: list[dict[str, str]]) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and value > 0:
        return value
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f"{field} must be a positive integer",
        )
    )
    return None


def _string_value(value: object, field: str, warnings: list[dict[str, str]]) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value:
        return value
    warnings.append(
        _warning("invalid_quality_runner_config_field", f"{field} must be a non-empty string")
    )
    return None


def _string_list(value: object, field: str, warnings: list[dict[str, str]]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f"{field} must be a list of non-empty strings",
        )
    )
    return []


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "path": ".quality-runner.toml"}
