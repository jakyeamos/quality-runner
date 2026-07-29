from __future__ import annotations

from typing import Any

from quality_runner.schema_constants import SECURITY_REVIEW_OBLIGATIONS_SCHEMA

_CATEGORY_MATCHES: dict[str, frozenset[str]] = {
    "security_api_route_auth_review": frozenset(
        {"missing-auth", "acl-check", "cross-tenant-id"}
    ),
    "security_auth_surface_review": frozenset(
        {"missing-auth", "auth-bypass", "jwt-handling"}
    ),
    "security_webhook_signature_review": frozenset(
        {"webhook-handler", "service-entry-point"}
    ),
    "security_dangerous_sink_review": frozenset(
        {"dangerous-sink", "rce", "dangerous-html"}
    ),
    "security_redirect_review": frozenset({"unsafe-redirect", "open-redirect"}),
    "security_secret_exposure_review": frozenset(
        {"secrets-exposure", "secret-in-fallback", "secret-in-log", "secret-env-var"}
    ),
    "security_dependency_risk_review": frozenset(),
    "security_rate_limit_review": frozenset(
        {"rate-limit-bypass", "expensive-api-abuse"}
    ),
}


def build_security_review_obligations(
    security_scan: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(security_scan, dict):
        return _empty_payload(status="unavailable")

    settings = security_scan.get("settings")
    enabled = not isinstance(settings, dict) or settings.get("enabled") is not False
    gates = security_scan.get("agent_review_gates")
    candidates = security_scan.get("candidates")
    candidate_items = (
        [item for item in candidates if isinstance(item, dict)]
        if isinstance(candidates, list)
        else []
    )
    gate_items = (
        [item for item in gates if isinstance(item, dict)] if isinstance(gates, list) else []
    )
    obligations = [
        _obligation_for_gate(gate, candidate_items)
        for gate in sorted(gate_items, key=lambda item: str(item.get("id") or ""))
        if isinstance(gate.get("id"), str) and gate["id"]
    ]
    return {
        "schema": SECURITY_REVIEW_OBLIGATIONS_SCHEMA,
        "run_id": security_scan.get("run_id")
        if isinstance(security_scan.get("run_id"), str)
        else None,
        "status": (
            "review-required"
            if enabled and obligations
            else ("no-obligations" if enabled else "disabled")
        ),
        "obligation_count": len(obligations),
        "obligations": obligations,
        "source": {"artifact": "security-scan.json", "selection": "agent_review_gates"},
    }


def validate_security_review_obligations(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if payload.get("schema") != SECURITY_REVIEW_OBLIGATIONS_SCHEMA:
        errors.append(
            "security review obligations schema must be "
            f"{SECURITY_REVIEW_OBLIGATIONS_SCHEMA}"
        )
    obligations = payload.get("obligations")
    if not isinstance(obligations, list):
        errors.append("security review obligations must be a list")
        return {"passed": False, "errors": errors}
    if payload.get("obligation_count") != len(obligations):
        errors.append("security review obligation count must match the list length")
    ids: set[str] = set()
    for index, obligation in enumerate(obligations):
        if not isinstance(obligation, dict):
            errors.append(f"obligation at index {index} is not an object")
            continue
        for field in ("id", "slice_id", "finding_id", "status"):
            if not isinstance(obligation.get(field), str) or not obligation[field]:
                errors.append(f"obligation at index {index} field {field} must be non-empty")
        obligation_id = obligation.get("id")
        if isinstance(obligation_id, str):
            if obligation_id in ids:
                errors.append(f"duplicate security review obligation id: {obligation_id}")
            ids.add(obligation_id)
        if not isinstance(obligation.get("scope"), dict):
            errors.append(f"obligation {obligation_id or index} scope must be an object")
        for field in ("review_instructions", "completion_criteria", "candidate_refs"):
            if not isinstance(obligation.get(field), list):
                errors.append(f"obligation {obligation_id or index} {field} must be a list")
    return {"passed": not errors, "errors": errors}


def _obligation_for_gate(
    gate: dict[str, Any], candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    gate_id = str(gate["id"])
    candidate_refs = [
        _candidate_ref(candidate)
        for candidate in candidates
        if _candidate_matches(gate_id, candidate)
    ]
    candidate_refs.sort(
        key=lambda item: (
            str(item.get("file") or ""),
            int(item.get("line") or 0),
            str(item["id"]),
        )
    )
    return {
        "id": gate_id,
        "slice_id": f"remediate-security-review-{gate_id.replace('_', '-')}",
        "finding_id": f"security-review-{gate_id.replace('_', '-')}",
        "status": str(gate.get("status") or "review-required"),
        "scope": gate.get("scope") if isinstance(gate.get("scope"), dict) else {},
        "review_instructions": _string_list(gate.get("review_instructions")),
        "completion_criteria": _string_list(gate.get("completion_criteria")),
        "candidate_refs": candidate_refs,
        "candidate_selection": {
            "method": "category-and-scope-contract",
            "categories": sorted(_CATEGORY_MATCHES.get(gate_id, frozenset())),
        },
    }


def _candidate_matches(gate_id: str, candidate: dict[str, Any]) -> bool:
    category = str(candidate.get("category") or "")
    if category in _CATEGORY_MATCHES.get(gate_id, frozenset()):
        return True
    file_path = candidate.get("file")
    if not isinstance(file_path, str):
        return False
    if gate_id == "security_dependency_risk_review":
        return file_path in {"package.json", "pnpm-lock.yaml", "pyproject.toml", "Cargo.toml"}
    if gate_id == "security_auth_surface_review":
        return file_path.startswith(("app/auth/", "auth/", "middleware", "proxy."))
    if gate_id == "security_webhook_signature_review":
        return "webhook" in file_path
    return False


def _candidate_ref(candidate: dict[str, Any]) -> dict[str, Any]:
    ref: dict[str, Any] = {}
    for field in ("id", "category", "file", "line", "fingerprint", "severity_hint"):
        value = candidate.get(field)
        if isinstance(value, (str, int)) and value != "":
            ref[field] = value
    return ref


def _string_list(value: object) -> list[str]:
    return (
        [item for item in value if isinstance(item, str) and item]
        if isinstance(value, list)
        else []
    )


def _empty_payload(*, status: str) -> dict[str, Any]:
    return {
        "schema": SECURITY_REVIEW_OBLIGATIONS_SCHEMA,
        "run_id": None,
        "status": status,
        "obligation_count": 0,
        "obligations": [],
        "source": {"artifact": "security-scan.json", "selection": "agent_review_gates"},
    }
