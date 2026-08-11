from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any


def disabled_timing(reason: str) -> dict[str, Any]:
    return {
        "cache_status": "disabled",
        "recomputed": False,
        "recompute_reason": reason,
    }


def recomputed_timing(started: float, *, reason: str) -> dict[str, Any]:
    return {
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "cache_status": "disabled",
        "recomputed": True,
        "recompute_reason": reason,
    }


def status_entry(
    *,
    tool: str,
    status: str,
    command: list[str] | None = None,
    exit_code: int | None = None,
    stderr_tail: str = "",
    stdout_tail: str = "",
    timing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"tool": tool, "status": status}
    if command is not None:
        entry["command"] = command
    if exit_code is not None:
        entry["exit_code"] = exit_code
    if stderr_tail:
        entry["stderr_tail"] = stderr_tail
    if stdout_tail:
        entry["stdout_tail"] = stdout_tail
    if timing:
        entry.update(timing)
    return entry
