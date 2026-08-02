from __future__ import annotations

from typing import Any, cast


def parse_security_section(value: object, warnings: list[dict[str, str]]) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(
            {
                "code": "invalid_quality_runner_config_field",
                "message": "quality_runner.security must be a table",
                "path": ".quality-runner.toml",
            }
        )
        return {}
    config = cast(dict[str, object], value)

    result: dict[str, Any] = {}
    if "enabled" in config:
        enabled = config.get("enabled")
        if isinstance(enabled, bool):
            result["enabled"] = enabled
        else:
            warnings.append(
                {
                    "code": "invalid_quality_runner_config_field",
                    "message": "quality_runner.security.enabled must be a boolean",
                    "path": ".quality-runner.toml",
                }
            )
    if "require_security_baseline" in config:
        require_baseline = config.get("require_security_baseline")
        if isinstance(require_baseline, bool):
            result["require_security_baseline"] = require_baseline
    if "agent_review_gates" in config:
        agent_review = config.get("agent_review_gates")
        if isinstance(agent_review, bool):
            result["agent_review_gates"] = agent_review
    owner_role = config.get("owner_role")
    if owner_role is not None:
        if isinstance(owner_role, str) and owner_role.strip():
            result["owner_role"] = owner_role.strip()
        else:
            warnings.append(
                {
                    "code": "invalid_quality_runner_config_field",
                    "message": "quality_runner.security.owner_role must be a non-empty string",
                    "path": ".quality-runner.toml",
                }
            )
    required = _string_list(config.get("required_capabilities"))
    if required:
        result["required_capabilities"] = required
    disabled = _string_list(config.get("disabled_rule_groups"))
    if disabled:
        result["disabled_rule_groups"] = disabled
    severity = config.get("severity")
    if isinstance(severity, dict):
        minimum = cast(dict[str, object], severity).get("minimum_agent_review")
        if isinstance(minimum, str) and minimum:
            result["severity"] = {"minimum_agent_review": minimum}
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str) and item]
