from __future__ import annotations

from typing import Any, Literal

AgentReviewMode = Literal["off", "auto", "parallel", "required"]

AGENT_REVIEW_MODES: tuple[AgentReviewMode, ...] = ("off", "auto", "parallel", "required")
DEFAULT_AGENT_REVIEW_MODE: AgentReviewMode = "auto"
RELEASE_PROFILE = "release"


def resolve_agent_review_mode(
    *,
    requested: str | None,
    profile: str | None,
    config: dict[str, Any],
) -> AgentReviewMode:
    """Resolve review policy, with release readiness taking precedence."""
    if profile == RELEASE_PROFILE:
        return "required"

    if requested is not None:
        return _validated_mode(requested, source="--agent-review-mode")

    skills = config.get("skills")
    configured = skills.get("agent_review_mode") if isinstance(skills, dict) else None
    if configured is not None:
        return _validated_mode(configured, source="quality_runner.skills.agent_review_mode")

    return DEFAULT_AGENT_REVIEW_MODE


def review_status_for_mode(
    *,
    mode: AgentReviewMode,
    unresolved: bool,
    rejected: bool,
) -> str:
    if rejected:
        return "review-rejected"
    if not unresolved:
        return "reviewed"
    if mode == "off":
        return "not-run"
    if mode in {"auto", "parallel"}:
        return "review-pending"
    return "review-required"


def review_blocks_readiness(skill_review: dict[str, Any] | None) -> bool:
    if not isinstance(skill_review, dict):
        return False
    return skill_review.get("status") in {"review-required", "review-rejected"}


def _validated_mode(value: object, *, source: str) -> AgentReviewMode:
    if value == "off":
        return "off"
    if value == "auto":
        return "auto"
    if value == "parallel":
        return "parallel"
    if value == "required":
        return "required"
    choices = ", ".join(AGENT_REVIEW_MODES)
    raise ValueError(f"{source} must be one of: {choices}")
