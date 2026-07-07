from __future__ import annotations

from typing import Any

CONFIG_FILE_NAME = ".quality-runner.toml"


def parse_skills_section(value: object, warnings: list[dict[str, str]]) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(_warning("quality_runner.skills must be a table"))
        return {}

    result: dict[str, Any] = {}
    enabled = value.get("enabled")
    if enabled is not None:
        if isinstance(enabled, bool):
            result["enabled"] = enabled
        else:
            warnings.append(_warning("quality_runner.skills.enabled must be a boolean"))

    active = _string_list(value.get("active"))
    if active:
        result["active"] = active

    local_skills = _local_skills(value.get("local"), warnings)
    if local_skills:
        result["local"] = local_skills

    return result


def _local_skills(value: object, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(_warning("quality_runner.skills.local must be a list of tables"))
        return []

    skills: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        skill_id = _non_empty_string(item.get("id"))
        path = _non_empty_string(item.get("path"))
        if not skill_id or not path:
            warnings.append(
                _warning(f"quality_runner.skills.local[{index}] must include id and path strings")
            )
            continue
        skill: dict[str, Any] = {"id": skill_id, "path": path}
        applies_to = _string_list(item.get("applies_to"))
        if applies_to:
            skill["applies_to"] = applies_to
        skills.append(skill)
    return skills


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
