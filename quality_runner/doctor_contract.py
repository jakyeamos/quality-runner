from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from quality_runner import __version__

DOCTOR_RESULT_SCHEMA = "quality-runner-doctor-result-v0.1"


def doctor_payload(*, include_environment: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": DOCTOR_RESULT_SCHEMA,
        "status": "ready",
        "version": __version__,
        "implementation_allowed": False,
    }
    if include_environment:
        payload["environment"] = {
            "cwd": str(Path.cwd()),
            "platform": platform.platform(),
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
        }
    return payload
