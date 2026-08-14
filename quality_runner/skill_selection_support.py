from __future__ import annotations


def _diagnostic_signals(signals: set[str], *, priority: set[str] | None = None) -> list[str]:
    meaningful = {token for token in signals if not token.isdigit()}
    prioritized = sorted(meaningful & (priority or set()))
    remainder = sorted(meaningful - set(prioritized))
    return [*prioritized, *remainder][:160]


def _global_warning(path: object, message: str) -> dict[str, str]:
    return {
        "code": "invalid_quality_runner_global_skill_config",
        "message": f"global Quality Skill config: {message}",
        "path": str(path) if path else "<global-quality-runner-config>",
    }
