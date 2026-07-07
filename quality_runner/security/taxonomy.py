from __future__ import annotations

SECURITY_TAXONOMY_CATEGORIES: tuple[str, ...] = (
    "missing-auth",
    "auth-bypass",
    "acl-check",
    "xss",
    "dangerous-html",
    "rce",
    "sql-injection",
    "ssrf",
    "path-traversal",
    "secrets-exposure",
    "insecure-crypto",
    "open-redirect",
    "unsafe-redirect",
    "public-endpoint",
    "service-entry-point",
    "webhook-handler",
    "iam-permissions",
    "jwt-handling",
    "env-exposure",
    "rate-limit-bypass",
    "cache-key-poisoning",
    "secret-env-var",
    "cross-tenant-id",
    "secret-in-fallback",
    "secret-in-log",
    "expensive-api-abuse",
    "dangerous-sink",
)

SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}

SECURITY_RESOLUTION_STATUSES: tuple[str, ...] = (
    "unreviewed",
    "review-required",
    "true-positive",
    "false-positive",
    "accepted-risk",
    "fixed",
    "stale",
    "superseded",
    "blocked",
)
