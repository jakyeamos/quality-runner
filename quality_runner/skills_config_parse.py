from __future__ import annotations

from typing import Any

from quality_runner.agent_review_policy import AGENT_REVIEW_MODES

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

    global_enabled = value.get("global_enabled")
    if global_enabled is not None:
        if isinstance(global_enabled, bool):
            result["global_enabled"] = global_enabled
        else:
            warnings.append(_warning("quality_runner.skills.global_enabled must be a boolean"))

    global_exclude = value.get("global_exclude")
    if global_exclude is not None:
        if isinstance(global_exclude, list) and all(
            isinstance(item, str) and item for item in global_exclude
        ):
            result["global_exclude"] = global_exclude
        else:
            warnings.append(
                _warning("quality_runner.skills.global_exclude must be a list of strings")
            )

    global_always = value.get("global_always")
    if global_always is not None:
        if isinstance(global_always, list) and all(
            isinstance(item, str) and item for item in global_always
        ):
            result["global_always"] = global_always
        else:
            warnings.append(
                _warning("quality_runner.skills.global_always must be a list of strings")
            )

    agent_review_mode = value.get("agent_review_mode")
    if agent_review_mode is not None:
        if isinstance(agent_review_mode, str) and agent_review_mode in AGENT_REVIEW_MODES:
            result["agent_review_mode"] = agent_review_mode
        else:
            warnings.append(
                _warning(
                    "quality_runner.skills.agent_review_mode must be one of: off, auto, parallel, required"
                )
            )

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
