from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

CONFIG_FILE_NAME = ".quality-runner.toml"
CONFIG_SCHEMA = "quality-runner-config-v0.1"


def load_repo_config(repo_root: Path) -> dict[str, Any]:
    path = repo_root.expanduser().resolve() / CONFIG_FILE_NAME
    if not path.exists():
        return _empty_config(path=None, warnings=[])

    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        return _empty_config(
            path=CONFIG_FILE_NAME,
            warnings=[
                _warning(
                    "invalid_quality_runner_config",
                    f"{CONFIG_FILE_NAME} could not be parsed as TOML: {error}",
                )
            ],
        )

    section = payload.get("quality_runner")
    if not isinstance(section, dict):
        return _empty_config(path=CONFIG_FILE_NAME, warnings=[])

    warnings: list[dict[str, str]] = []
    default_profile = _string_value(
        section.get("default_profile"), "quality_runner.default_profile", warnings
    )
    required = _string_list(
        section.get("required_capabilities"), "quality_runner.required_capabilities", warnings
    )
    exceptions = _accepted_exceptions(section.get("accepted_exceptions"), warnings)
    return _config(
        path=CONFIG_FILE_NAME,
        default_profile=default_profile,
        required_capabilities=required,
        required_capabilities_configured="required_capabilities" in section,
        accepted_exceptions=exceptions,
        warnings=warnings,
    )


# fmt: off
def _config(
    *, path: str | None, default_profile: str | None, required_capabilities: list[str], required_capabilities_configured: bool, accepted_exceptions: list[dict[str, str]], warnings: list[dict[str, str]],
) -> dict[str, Any]:
    return dict(
        schema=CONFIG_SCHEMA, path=path, default_profile=default_profile, required_capabilities=required_capabilities, required_capabilities_configured=required_capabilities_configured, accepted_exceptions=accepted_exceptions, warnings=warnings,
    )
# fmt: on


def _empty_config(*, path: str | None, warnings: list[dict[str, str]]) -> dict[str, Any]:
    return _config(
        path=path,
        default_profile=None,
        required_capabilities=[],
        required_capabilities_configured=False,
        accepted_exceptions=[],
        warnings=warnings,
    )


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


def _accepted_exceptions(value: object, warnings: list[dict[str, str]]) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(
            _warning(
                "invalid_quality_runner_config_field",
                "quality_runner.accepted_exceptions must be a list of tables",
            )
        )
        return []

    accepted: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            _accepted_exception_warning(index, warnings)
            continue
        capability = item.get("capability")
        reason = item.get("reason")
        expires = item.get("expires")
        if (
            isinstance(capability, str)
            and capability
            and isinstance(reason, str)
            and reason
            and isinstance(expires, str)
            and expires
        ):
            accepted.append(dict(capability=capability, reason=reason, expires=expires))
        else:
            _accepted_exception_warning(index, warnings)
    return accepted


def _accepted_exception_warning(index: int, warnings: list[dict[str, str]]) -> None:
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f"quality_runner.accepted_exceptions[{index}] must include capability, reason, and expires strings",
        )
    )


def _warning(code: str, message: str) -> dict[str, str]:
    return dict(code=code, message=message, path=CONFIG_FILE_NAME)
