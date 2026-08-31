from __future__ import annotations

import time
from typing import Any


def bounded_output(value: object, limit: int = 20_000) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = value if isinstance(value, str) else ""
    return text[-limit:]


def timed_result(payload: dict[str, Any], started: float) -> dict[str, Any]:
    payload["duration_seconds"] = round(time.monotonic() - started, 6)
    return payload
