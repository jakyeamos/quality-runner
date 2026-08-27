from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

MAX_FRESH_EVIDENCE_AGE = timedelta(hours=24)
CAPABILITY_EVIDENCE_STATES = {
    "configured",
    "covered",
    "fresh_passing",
    "failed",
    "blocked",
    "unavailable",
    "not_applicable",
}
BLOCKING_CAPABILITIES = frozenset(
    {
        "formatter",
        "lint",
        "typecheck",
        "tests",
        "dead_code",
        "failure_visibility",
    }
)


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
        "failure_visibility": (
            "failure visibility",
            "failure-visibility",
            "failure_visibility",
            "failure paths",
            "failure-paths",
        ),
        "pre_pr": ("pull request", "pre-pr", "pre pr"),
        "pre_cr": ("pre-cr", "pre cr"),
    }.get(capability_id, (capability_id,))
    for check in cast(list[object], checks):
        if not isinstance(check, dict):
            continue
        typed_check = cast(dict[str, Any], check)
        name = typed_check.get("name")
        if not isinstance(name, str):
            continue
        normalized = name.lower()
        if any(term in normalized for term in terms):
            optional = {
                key: value
                for key, value in {
                    "head_sha": _optional_string(typed_check.get("head_sha")),
                    "ref": _optional_string(typed_check.get("ref")),
                    "workflow_run_id": _optional_string(typed_check.get("workflow_run_id")),
                    "captured_at": _optional_string(typed_check.get("captured_at")),
                }.items()
                if value is not None
            }
            return {
                "name": name,
                "status": _optional_string(typed_check.get("status")),
                "conclusion": _optional_string(typed_check.get("conclusion")),
                "url": _optional_string(typed_check.get("url")),
                **optional,
            }
    return None


def capability_evidence_state(
    *,
    scan: dict[str, Any],
    ci_status: dict[str, str | None] | None,
) -> str:
    """Project capability evidence without turning stale CI into current truth."""
    if ci_status is None:
        return "configured"
    if not _current_fresh_ci_evidence(scan=scan, ci_status=ci_status):
        return "covered"
    conclusion = ci_status.get("conclusion")
    if conclusion == "success":
        return "fresh_passing"
    if isinstance(conclusion, str) and conclusion:
        return "failed"
    return "covered"


def local_capability_evidence_state(result: object) -> str:
    return {
        "passed": "fresh_passing",
        "failed": "failed",
        "blocked": "blocked",
    }.get(str(result), "configured")


def _current_fresh_ci_evidence(
    *,
    scan: dict[str, Any],
    ci_status: dict[str, str | None],
) -> bool:
    provenance_value = scan.get("git_provenance") or scan.get("provenance")
    provenance = (
        cast(dict[str, Any], provenance_value) if isinstance(provenance_value, dict) else {}
    )
    head_sha = provenance.get("head_sha")
    branch = provenance.get("branch")
    if not isinstance(head_sha, str) or not head_sha or ci_status.get("head_sha") != head_sha:
        return False
    if not isinstance(branch, str) or not branch:
        return False
    if ci_status.get("ref") not in {branch, f"refs/heads/{branch}"}:
        return False
    if not ci_status.get("workflow_run_id"):
        return False
    captured_at = ci_status.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at:
        return False
    try:
        captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if captured.tzinfo is None:
        return False
    now = datetime.now(UTC)
    return captured <= now + timedelta(minutes=5) and now - captured <= MAX_FRESH_EVIDENCE_AGE


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
