from __future__ import annotations

from typing import Any


def verification_state(
    *,
    discovery: str,
    ci_status: dict[str, str | None] | None,
) -> dict[str, str]:
    if ci_status is None:
        return {"discovery": discovery, "execution": "not-run", "result": "unknown"}

    conclusion = ci_status.get("conclusion")
    if conclusion == "success":
        result = "passed"
    elif isinstance(conclusion, str) and conclusion:
        result = "failed"
    else:
        result = "unknown"
    return {"discovery": discovery, "execution": "ci-executed", "result": result}


def matching_ci_status(
    scan: dict[str, Any],
    capability_id: str,
) -> dict[str, str | None] | None:
    checks = scan.get("ci_checks")
    if not isinstance(checks, list):
        return None
    terms = {
        "formatter": ("format", "fmt", "prettier"),
        "lint": ("lint",),
        "typecheck": ("typecheck", "type-check", "types"),
        "tests": ("test", "tests"),
        "build": ("build",),
        "dead_code": ("dead", "unused", "knip", "vulture"),
        "runtime_smoke": ("smoke",),
        "pre_pr": ("pull request", "pre-pr", "pre pr"),
        "pre_cr": ("pre-cr", "pre cr"),
    }.get(capability_id, (capability_id,))
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = check.get("name")
        if not isinstance(name, str):
            continue
        normalized = name.lower()
        if any(term in normalized for term in terms):
            return {
                "name": name,
                "status": _optional_string(check.get("status")),
                "conclusion": _optional_string(check.get("conclusion")),
                "url": _optional_string(check.get("url")),
            }
    return None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
