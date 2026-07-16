from __future__ import annotations

import sys
from typing import Any


def environment() -> dict[str, str | bool | None]:
    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "sandbox": None,
    }


def timeout_output_diagnostics(*, stdout: str, stderr: str) -> dict[str, Any]:
    if stdout or stderr:
        return {"timeout_output_status": "captured-partial-output"}
    return {"timeout_output_status": "timeout-with-no-output"}


def int_result(value: object) -> int:
    return value if isinstance(value, int) else 1
