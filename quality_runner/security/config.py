from __future__ import annotations

from typing import Any

DEFAULT_REQUIRED_SECURITY_CAPABILITIES: tuple[str, ...] = ()

DEFAULT_AGENT_REVIEW_GATES: tuple[str, ...] = (
    "security_api_route_auth_review",
    "security_auth_surface_review",
    "security_webhook_signature_review",
    "security_dangerous_sink_review",
    "security_redirect_review",
    "security_secret_exposure_review",
    "security_dependency_risk_review",
    "security_rate_limit_review",
    "security_cross_tenant_access_review",
)


def security_settings(config: dict[str, Any]) -> dict[str, Any]:
    section = config.get("security")
    if not isinstance(section, dict):
        return _default_security_settings(configured=False)

    enabled = section.get("enabled")
    require_baseline = section.get("require_security_baseline")
    agent_review = section.get("agent_review_gates")
    required = section.get("required_capabilities")
    disabled_groups = section.get("disabled_rule_groups")
    severity = section.get("severity")
    owner_role = section.get("owner_role")
    minimum_agent_review = "medium"
    if isinstance(severity, dict):
        value = severity.get("minimum_agent_review")
        if isinstance(value, str) and value:
            minimum_agent_review = value

    return {
        "enabled": enabled is not False,
        "require_security_baseline": require_baseline is not False,
        "agent_review_gates": agent_review is not False,
        "required_capabilities": _string_list(required)
        or list(DEFAULT_REQUIRED_SECURITY_CAPABILITIES),
        "disabled_rule_groups": _string_list(disabled_groups),
        "minimum_agent_review": minimum_agent_review,
        "owner_role": owner_role
        if isinstance(owner_role, str) and owner_role
        else "security-maintainer",
        "configured": True,
    }


def _default_security_settings(*, configured: bool) -> dict[str, Any]:
    return {
        "enabled": True,
        "require_security_baseline": True,
        "agent_review_gates": True,
        "required_capabilities": list(DEFAULT_REQUIRED_SECURITY_CAPABILITIES),
        "disabled_rule_groups": [],
        "minimum_agent_review": "medium",
        "owner_role": "security-maintainer",
        "configured": configured,
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
