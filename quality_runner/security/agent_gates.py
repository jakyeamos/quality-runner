from __future__ import annotations

from typing import Any

AGENT_REVIEW_GATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "security_api_route_auth_review": {
        "scope": {
            "paths": ["app/api/**", "pages/api/**", "src/routes/**", "routes/**"],
            "categories": ["missing-auth", "acl-check", "cross-tenant-id"],
        },
        "review_instructions": [
            "Identify public route handlers.",
            "Check for direct auth guards, framework guards, or route-level middleware.",
            "Check resource-level authorization, not just login presence.",
            "Record false positives with evidence.",
        ],
        "completion_criteria": [
            "Each candidate is marked true-positive, false-positive, accepted-risk, fixed, or blocked.",
            "Any fix includes a verification command or test.",
        ],
        "trigger": "api_routes",
    },
    "security_auth_surface_review": {
        "scope": {
            "paths": ["app/**", "src/**", "middleware.*", "auth/**"],
            "categories": ["missing-auth", "auth-bypass", "jwt-handling"],
        },
        "review_instructions": [
            "Map authentication entry points and session handling.",
            "Confirm protected routes cannot be reached without auth.",
            "Review JWT/session validation and expiry handling.",
        ],
        "completion_criteria": [
            "Auth surfaces documented with guard evidence.",
            "Unresolved auth bypass candidates dispositioned.",
        ],
        "trigger": "api_routes",
    },
    "security_webhook_signature_review": {
        "scope": {
            "paths": ["**/webhook/**", "**/webhooks/**", "app/api/**"],
            "categories": ["webhook-handler", "service-entry-point"],
        },
        "review_instructions": [
            "List webhook handlers and their signature verification.",
            "Confirm verification occurs before mutations or side effects.",
            "Check replay protection where applicable.",
        ],
        "completion_criteria": [
            "Each webhook handler has verified signature check or documented exception.",
        ],
        "trigger": "webhooks",
    },
    "security_dangerous_sink_review": {
        "scope": {
            "paths": ["**/*"],
            "categories": ["dangerous-sink", "rce", "dangerous-html"],
        },
        "review_instructions": [
            "Review eval/exec/spawn/deserialization/template sinks.",
            "Confirm user input cannot reach sinks without validation.",
        ],
        "completion_criteria": [
            "High-confidence sink candidates reviewed and dispositioned.",
        ],
        "trigger": "dangerous_sinks",
    },
    "security_redirect_review": {
        "scope": {
            "paths": ["app/**", "pages/**", "src/**"],
            "categories": ["unsafe-redirect", "open-redirect"],
        },
        "review_instructions": [
            "Find redirects using request/query/user-controlled values.",
            "Confirm allowlist or same-origin checks exist.",
        ],
        "completion_criteria": [
            "Redirect candidates reviewed with allowlist evidence or fixes.",
        ],
        "trigger": "redirects",
    },
    "security_secret_exposure_review": {
        "scope": {
            "paths": ["**/*"],
            "categories": [
                "secrets-exposure",
                "secret-in-fallback",
                "secret-in-log",
                "secret-env-var",
            ],
        },
        "review_instructions": [
            "Review hardcoded secrets, fallback values, and sensitive logs.",
            "Rotate confirmed secrets and move to secure configuration.",
        ],
        "completion_criteria": [
            "Confirmed secrets rotated; false positives documented.",
        ],
        "trigger": "secrets",
    },
    "security_dependency_risk_review": {
        "scope": {
            "paths": ["package.json", "pnpm-lock.yaml", "pyproject.toml", "Cargo.toml"],
            "categories": ["service-entry-point"],
        },
        "review_instructions": [
            "Review dependency audit output if available.",
            "Prioritize reachable high/critical CVEs in runtime dependencies.",
        ],
        "completion_criteria": [
            "High-risk dependency issues dispositioned with upgrade or mitigation plan.",
        ],
        "trigger": "dependency_manifest",
    },
    "security_rate_limit_review": {
        "scope": {
            "paths": ["app/api/**", "pages/api/**", "src/routes/**"],
            "categories": ["rate-limit-bypass", "expensive-api-abuse"],
        },
        "review_instructions": [
            "Identify public or expensive endpoints.",
            "Confirm rate limiting or quota controls exist.",
        ],
        "completion_criteria": [
            "Expensive/public routes have rate limit evidence or fixes.",
        ],
        "trigger": "expensive_api",
    },
    "security_publication_visibility_review": {
        "scope": {
            "paths": ["app/**", "src/**", "pages/**", "content/**", "media/**"],
            "categories": ["publication-boundary", "visibility-boundary", "dangerous-html"],
        },
        "review_instructions": [
            "Map public, private, draft, and published content boundaries.",
            "Confirm authorization and visibility invariants for readers, media, and APIs.",
            "Trace raw HTML/content provenance and confirm sanitization before rendering.",
            "Confirm publication immutability, versioning, and rollback behavior.",
        ],
        "completion_criteria": [
            "Every publication and visibility path has an authorization or explicit public-access decision.",
            "Raw content provenance and sanitization evidence are recorded or have an accepted-risk disposition.",
            "Published content has immutability, versioning, or rollback evidence.",
            "Public and private media access paths have explicit authorization and visibility evidence.",
        ],
        "trigger": "publication_visibility",
    },
    "security_cross_tenant_access_review": {
        "scope": {
            "paths": ["app/api/**", "src/**", "services/**"],
            "categories": ["cross-tenant-id", "acl-check"],
        },
        "review_instructions": [
            "Trace resource access by tenant/org identifiers.",
            "Confirm queries enforce tenant scoping.",
        ],
        "completion_criteria": [
            "Cross-tenant access paths reviewed with ACL evidence.",
        ],
        "trigger": "api_routes",
    },
}


def build_agent_review_gates(
    *,
    surfaces: dict[str, bool],
    candidates: list[dict[str, Any]],
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    if not settings.get("agent_review_gates", True):
        return []

    triggers = _active_triggers(surfaces, candidates)
    gates: list[dict[str, Any]] = []
    minimum = settings.get("minimum_agent_review", "medium")
    for gate_id, definition in AGENT_REVIEW_GATE_DEFINITIONS.items():
        trigger = definition.get("trigger")
        if trigger not in triggers:
            continue
        if not _meets_minimum_severity(gate_id, candidates, minimum):
            continue
        gates.append(
            {
                "id": gate_id,
                "type": "agent_review",
                "capability_kind": "agent_review",
                "status": "review-required",
                "required_by": "security-baseline",
                "scope": definition["scope"],
                "review_instructions": definition["review_instructions"],
                "completion_criteria": definition["completion_criteria"],
                "verification_state": {
                    "discovery": "review-required",
                    "execution": "agent-required",
                    "result": "unknown",
                },
            }
        )
    return gates


def _active_triggers(
    surfaces: dict[str, bool],
    candidates: list[dict[str, Any]],
) -> set[str]:
    categories = {candidate.get("category") for candidate in candidates}
    triggers: set[str] = set()
    if surfaces.get("api_routes"):
        triggers.add("api_routes")
    if surfaces.get("dependency_manifest"):
        triggers.add("dependency_manifest")
    if "webhook-handler" in categories or surfaces.get("webhooks"):
        triggers.add("webhooks")
    if "dangerous-sink" in categories or surfaces.get("dangerous_sinks"):
        triggers.add("dangerous_sinks")
    if any("redirect" in str(category) for category in categories):
        triggers.add("redirects")
    if any(
        str(category).startswith("secret") or category == "secrets-exposure"
        for category in categories
    ):
        triggers.add("secrets")
    if "expensive-api-abuse" in categories:
        triggers.add("expensive_api")
    if surfaces.get("publication_visibility"):
        triggers.add("publication_visibility")
    return triggers


def _meets_minimum_severity(
    gate_id: str,
    candidates: list[dict[str, Any]],
    minimum: str,
) -> bool:
    if gate_id in {
        "security_dependency_risk_review",
        "security_auth_surface_review",
        "security_api_route_auth_review",
        "security_publication_visibility_review",
    }:
        return True
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    minimum_rank = order.get(minimum, 2)
    for candidate in candidates:
        severity = candidate.get("severity_hint")
        if not isinstance(severity, str):
            continue
        if order.get(severity, 99) <= minimum_rank:
            related = _gate_matches_candidate(gate_id, candidate)
            if related:
                return True
    return gate_id in {
        "security_api_route_auth_review",
        "security_auth_surface_review",
        "security_dependency_risk_review",
    }


def _gate_matches_candidate(gate_id: str, candidate: dict[str, Any]) -> bool:
    category = str(candidate.get("category") or "")
    mapping = {
        "security_dangerous_sink_review": {"dangerous-sink", "rce"},
        "security_redirect_review": {"unsafe-redirect", "open-redirect"},
        "security_secret_exposure_review": {
            "secrets-exposure",
            "secret-in-fallback",
            "secret-in-log",
            "secret-env-var",
        },
        "security_webhook_signature_review": {"webhook-handler"},
        "security_rate_limit_review": {"expensive-api-abuse", "rate-limit-bypass"},
        "security_cross_tenant_access_review": {"cross-tenant-id", "acl-check"},
    }
    return category in mapping.get(gate_id, set())
