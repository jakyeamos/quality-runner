from __future__ import annotations

from typing import Any


def parse_readiness_section(
    value: object,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(_warning("quality_runner.readiness must be a table"))
        return {}
    evidence_file = value.get("evidence_file")
    if evidence_file is not None and (not isinstance(evidence_file, str) or not evidence_file):
        warnings.append(
            _warning("quality_runner.readiness.evidence_file must be a non-empty string")
        )
        return {}
    return {"evidence_file": evidence_file} if isinstance(evidence_file, str) else {}


def _warning(message: str) -> dict[str, str]:
    return {
        "code": "invalid_quality_runner_config_field",
        "message": message,
        "path": ".quality-runner.toml",
    }
