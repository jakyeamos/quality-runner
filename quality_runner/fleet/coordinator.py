from __future__ import annotations

from collections.abc import Callable
from typing import Any

from quality_runner.refresh_timeout import workflow_deadline

MAX_DYNAMIC_COMMANDS = 8
DEPENDENCY_SETUP_BUDGET_SECONDS = 120
WORKTREE_AND_CLEANUP_BUDGET_SECONDS = 90
MINIMUM_REPOSITORY_WATCHDOG_SECONDS = 300


def dynamic_repository_watchdog_seconds(per_command_timeout_seconds: int) -> int:
    command_budget = MAX_DYNAMIC_COMMANDS * max(per_command_timeout_seconds, 1)
    return max(
        MINIMUM_REPOSITORY_WATCHDOG_SECONDS,
        command_budget + DEPENDENCY_SETUP_BUDGET_SECONDS + WORKTREE_AND_CLEANUP_BUDGET_SECONDS,
    )


def coordinate_dynamic_result(
    *,
    build: Callable[..., dict[str, Any]],
    coordinator_watchdog_timeout_seconds: int | float | None = None,
    **builder_arguments: Any,
) -> dict[str, Any]:
    if builder_arguments.get("enabled") is not True:
        return build(**builder_arguments)
    per_command_timeout = int(builder_arguments["timeout_seconds"])
    watchdog_timeout = (
        coordinator_watchdog_timeout_seconds
        if coordinator_watchdog_timeout_seconds is not None
        else dynamic_repository_watchdog_seconds(per_command_timeout)
    )
    repository = builder_arguments.get("repository", {})
    target = repository.get("target_branch", {}) if isinstance(repository, dict) else {}
    try:
        with workflow_deadline(
            seconds=watchdog_timeout,
            reason=(
                "repository dynamic verification exceeded the coordinator "
                f"watchdog of {watchdog_timeout} seconds"
            ),
        ):
            return build(**builder_arguments)
    except TimeoutError as error:
        return {
            "status": "timeout",
            "selected": True,
            "reason": str(error),
            "timeout_scope": "repository_dynamic",
            "watchdog_timeout_seconds": watchdog_timeout,
            "per_command_timeout_seconds": per_command_timeout,
            "target_branch": target.get("branch") if isinstance(target, dict) else None,
            "target_head": target.get("head") if isinstance(target, dict) else None,
            "commands": [],
            "implementation_allowed": False,
        }
