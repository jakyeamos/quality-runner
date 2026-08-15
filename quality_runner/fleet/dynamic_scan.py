from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.discovery import inspect_repo
from quality_runner.fleet.coordinator import MAX_DYNAMIC_COMMANDS

ALLOWED_DYNAMIC_CAPABILITIES = {
    "lint",
    "typecheck",
    "tests",
    "formatter",
    "dead_code",
    "runtime_smoke",
    "pre_cr",
}


def quality_commands_from_worktree(
    worktree: Path, *, run_id: str
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        scan = inspect_repo(worktree, run_id, cache_mode="disabled")
        commands = quality_commands_from_scan({"scan": scan})
    except (OSError, ValueError) as error:
        return [], str(error)
    return [_dynamic_runtime_command(command) for command in commands], None


def _dynamic_runtime_command(command: dict[str, Any]) -> dict[str, Any]:
    """Use the project root on sys.path when executing bare pytest entry points."""
    text = command.get("command")
    if command.get("id") == "tests" and text == "pytest -q":
        return {**command, "command": "python3 -m pytest -q"}
    return command


def quality_commands_from_scan(repository: dict[str, Any]) -> list[dict[str, Any]]:
    scan = repository.get("scan")
    if not isinstance(scan, dict):
        return []
    commands = scan.get("quality_commands")
    if not isinstance(commands, list):
        return []
    candidates = [
        item
        for item in commands
        if isinstance(item, dict) and item.get("id") in ALLOWED_DYNAMIC_CAPABILITIES
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        grouped.setdefault(str(candidate["id"]), []).append(candidate)

    selected: list[dict[str, Any]] = []
    for capability_commands in grouped.values():
        root_commands = [item for item in capability_commands if _is_root_command(item)]
        selected.extend(root_commands[:1] if root_commands else capability_commands)

    if len(selected) > MAX_DYNAMIC_COMMANDS:
        raise ValueError(
            f"dynamic selection found {len(selected)} non-aggregated dynamic commands; "
            "define root aggregate quality scripts so the bounded audit can verify complete coverage"
        )
    return selected


def _is_root_command(command: dict[str, Any]) -> bool:
    source = command.get("source")
    if not isinstance(source, str) or not source:
        return True
    source_path = source.split(":", maxsplit=1)[0]
    return "/" not in source_path
