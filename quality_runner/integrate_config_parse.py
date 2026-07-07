from __future__ import annotations

from typing import Any


def parse_integrate_section(
    value: object,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(
            _warning(
                "invalid_quality_runner_config_field",
                "quality_runner.integrate must be a table",
            )
        )
        return {}

    result: dict[str, Any] = {}
    enabled = value.get("enabled")
    if enabled is not None:
        if isinstance(enabled, bool):
            result["enabled"] = enabled
        else:
            warnings.append(
                _warning(
                    "invalid_quality_runner_config_field",
                    "quality_runner.integrate.enabled must be a boolean",
                )
            )
    registration_globs = _string_list(
        value.get("registration_globs"),
        "quality_runner.integrate.registration_globs",
        warnings,
    )
    entrypoint_globs = _string_list(
        value.get("entrypoint_globs"),
        "quality_runner.integrate.entrypoint_globs",
        warnings,
    )
    if registration_globs:
        result["registration_globs"] = registration_globs
    if entrypoint_globs:
        result["entrypoint_globs"] = entrypoint_globs
    return result


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
