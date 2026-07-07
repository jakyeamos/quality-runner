from __future__ import annotations

SECURITY_COMMAND_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "security_secrets_scan": (
        "gitleaks",
        "detect-secrets",
        "secret",
        "secrets",
        "trufflehog",
    ),
    "security_dependency_audit": (
        "audit",
        "pip-audit",
        "cargo audit",
        "snyk",
        "osv-scanner",
        "trivy",
    ),
    "security_static_analysis": (
        "semgrep",
        "bandit",
        "gosec",
        "trivy",
        "sast",
    ),
}

SECURITY_SCRIPT_ALIASES: dict[str, tuple[str, ...]] = {
    "security_secrets_scan": (
        "secret-scan",
        "secret_scan",
        "secrets",
        "gitleaks",
        "detect-secrets",
    ),
    "security_dependency_audit": (
        "audit:security",
        "dependency-audit",
        "dependency_audit",
        "security-audit",
    ),
    "security_static_analysis": (
        "security-scan",
        "security_scan",
        "semgrep",
        "sast",
        "bandit",
    ),
}

RECOMMENDED_COMMANDS: dict[str, list[str]] = {
    "security_secrets_scan": ["gitleaks detect --source .", "detect-secrets scan"],
    "security_dependency_audit": [
        "pnpm audit --audit-level high",
        "npm audit --audit-level high",
        "pip-audit",
        "cargo audit",
    ],
    "security_static_analysis": ["semgrep --config auto", "bandit -r .", "gosec ./..."],
}

AGENT_REVIEW_CAPABILITY_IDS = {
    "security_auth_surface_review",
    "security_api_route_auth_review",
    "security_webhook_signature_review",
    "security_dangerous_sink_review",
    "security_redirect_review",
    "security_secret_exposure_review",
    "security_dependency_risk_review",
    "security_rate_limit_review",
    "security_cross_tenant_access_review",
}
