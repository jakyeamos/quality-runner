from __future__ import annotations

import hashlib
import re
from typing import Any

from quality_runner.evidence_redaction import (
    SECRET_ASSIGNMENT_PATTERN,
    SECRET_FALLBACK_PATTERN,
    SECRET_LOG_PATTERN,
    SecretAssignmentSpan,
    analyze_secret_like_source_lines,
    redact_secret_like_literals,
)
from quality_runner.security.taxonomy import SECURITY_TAXONOMY_CATEGORIES

_CANDIDATE_ID = 0

SECRET_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    (
        "secrets-exposure",
        SECRET_ASSIGNMENT_PATTERN,
        "high",
        "Hardcoded secret-like assignment detected.",
    ),
    (
        "secret-in-fallback",
        SECRET_FALLBACK_PATTERN,
        "medium",
        "Secret-like fallback value in expression.",
    ),
    (
        "secret-in-log",
        SECRET_LOG_PATTERN,
        "medium",
        "Sensitive value may be logged.",
    ),
)

DANGEROUS_SINK_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    ("dangerous-sink", r"\beval\s*\(", "high", "eval() executes arbitrary code."),
    ("dangerous-sink", r"\bexec\s*\(", "high", "exec() executes arbitrary code."),
    ("dangerous-sink", r"(?:child_process\.)?spawn\s*\(", "high", "Process spawn sink."),
    ("dangerous-sink", r"os\.system\s*\(", "high", "Shell command execution sink."),
    (
        "dangerous-sink",
        r"subprocess\.(?:call|run|Popen)\s*\(",
        "high",
        "Subprocess execution sink.",
    ),
    ("dangerous-sink", r"dangerouslySetInnerHTML", "high", "Unsafe HTML injection sink."),
    ("dangerous-sink", r"pickle\.loads?\s*\(", "high", "Unsafe deserialization sink."),
    ("dangerous-sink", r"yaml\.load\s*\(", "medium", "YAML load without safe loader."),
)

REDIRECT_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    (
        "unsafe-redirect",
        r"(?i)(?:redirect|location\.href|window\.location|res\.redirect|NextResponse\.redirect).*(?:req\.|request\.|query\.|params\.|searchParams)",
        "medium",
        "Redirect may use user-controlled URL input.",
    ),
    (
        "open-redirect",
        r"(?i)redirect\s*\(\s*(?:req\.|request\.|query\.|params\.)",
        "medium",
        "Open redirect candidate without visible allowlist.",
    ),
)

ENV_EXPOSURE_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    (
        "env-exposure",
        r"(?i)(?:NEXT_PUBLIC_|VITE_|NUXT_PUBLIC_|PUBLIC_)[A-Z0-9_]*(?:SECRET|TOKEN|PRIVATE|KEY)[A-Z0-9_]*",
        "high",
        "Public env prefix combined with sensitive name pattern.",
    ),
    (
        "secret-env-var",
        r"(?i)process\.env\.[A-Z0-9_]*(?:SECRET|TOKEN|PRIVATE|KEY)[A-Z0-9_]*",
        "medium",
        "Secret-like environment variable access.",
    ),
)

EXPENSIVE_API_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    (
        "expensive-api-abuse",
        r"(?i)(?:openai|anthropic|stripe|twilio|sendgrid|resend)\.",
        "medium",
        "Expensive external API call site.",
    ),
)

WEBHOOK_PATTERN = re.compile(r"(?i)webhook")
SIGNATURE_TERMS = ("signature", "hmac", "verify", "stripe-signature", "x-hub-signature")
_SECRET_EVIDENCE_CATEGORIES = frozenset({"secrets-exposure", "secret-in-fallback", "secret-in-log"})


def scan_security_candidates(
    *,
    scanned_files: list[dict[str, Any]],
    disabled_groups: list[str],
    surfaces: dict[str, bool],
) -> list[dict[str, Any]]:
    global _CANDIDATE_ID
    candidates: list[dict[str, Any]] = []
    disabled = set(disabled_groups)
    additional_candidates: list[tuple[str, str, str, str, int, str, str]] = []

    for file_info in scanned_files:
        relative_path = file_info["path"]
        lines = file_info["lines"]
        source_analysis = analyze_secret_like_source_lines(lines)
        evidence_lines = source_analysis.lines
        legacy_assignment_lines = _legacy_span_lines(
            source_analysis.assignment_spans, lines, SECRET_ASSIGNMENT_PATTERN
        )
        legacy_fallback_lines = _legacy_span_lines(
            source_analysis.fallback_spans, lines, SECRET_FALLBACK_PATTERN
        )
        for line_number, line in enumerate(lines, start=1):
            if "secrets" in disabled and "secret" in line.lower():
                continue
            for pattern_group in (
                SECRET_PATTERNS,
                DANGEROUS_SINK_PATTERNS,
                REDIRECT_PATTERNS,
                ENV_EXPOSURE_PATTERNS,
            ):
                category = pattern_group[0][0]
                group_name = _group_for_category(category)
                if group_name in disabled:
                    continue
                for cat, pattern, severity, description in pattern_group:
                    if cat == "secrets-exposure" and line_number not in legacy_assignment_lines:
                        continue
                    if cat == "secret-in-fallback" and line_number not in legacy_fallback_lines:
                        continue
                    if re.search(pattern, line):
                        candidates.append(
                            _candidate(
                                category=cat,
                                severity=severity,
                                confidence=_confidence_for_match(cat, line),
                                file=relative_path,
                                line=line_number,
                                evidence=_candidate_evidence(cat, evidence_lines[line_number - 1]),
                                description=description,
                                requires_agent_review=_requires_agent_review(cat),
                            )
                        )

        if "secrets" not in disabled:
            additional_candidates.extend(
                _additional_span_candidates(
                    category="secrets-exposure",
                    severity="high",
                    description="Hardcoded secret-like assignment detected.",
                    relative_path=relative_path,
                    evidence_lines=evidence_lines,
                    source_lines=lines,
                    spans=source_analysis.assignment_spans,
                    legacy_lines=legacy_assignment_lines,
                )
            )
            additional_candidates.extend(
                _additional_span_candidates(
                    category="secret-in-fallback",
                    severity="medium",
                    description="Secret-like fallback value in expression.",
                    relative_path=relative_path,
                    evidence_lines=evidence_lines,
                    source_lines=lines,
                    spans=source_analysis.fallback_spans,
                    legacy_lines=legacy_fallback_lines,
                )
            )

        if surfaces.get("api_routes") and "expensive-api" not in disabled:
            for cat, pattern, severity, description in EXPENSIVE_API_PATTERNS:
                for line_number, line in enumerate(lines, start=1):
                    if not re.search(pattern, line):
                        continue
                    if not _nearby_auth_signals(lines, line_number):
                        candidates.append(
                            _candidate(
                                category=cat,
                                severity=severity,
                                confidence="medium",
                                file=relative_path,
                                line=line_number,
                                evidence=_candidate_evidence(cat, evidence_lines[line_number - 1]),
                                description=description,
                                requires_agent_review=True,
                            )
                        )

        if (
            (
                WEBHOOK_PATTERN.search(relative_path)
                or any(WEBHOOK_PATTERN.search(line) for line in lines[:200])
            )
            and "webhook" not in disabled
            and not _has_signature_verification(lines)
        ):
            candidates.append(
                _candidate(
                    category="webhook-handler",
                    severity="medium",
                    confidence="medium",
                    file=relative_path,
                    line=1,
                    evidence=f"Webhook handler in {relative_path} without obvious signature verification.",
                    description="Webhook route may lack signature verification.",
                    requires_agent_review=True,
                )
            )

    for (
        category,
        severity,
        confidence,
        relative_path,
        line,
        evidence,
        description,
    ) in additional_candidates:
        candidates.append(
            _candidate(
                category=category,
                severity=severity,
                confidence=confidence,
                file=relative_path,
                line=line,
                evidence=evidence,
                description=description,
                requires_agent_review=_requires_agent_review(category),
            )
        )

    _CANDIDATE_ID = 0
    return _dedupe_candidates(candidates)


def _candidate(
    *,
    category: str,
    severity: str,
    confidence: str,
    file: str,
    line: int,
    evidence: str,
    description: str,
    requires_agent_review: bool,
) -> dict[str, Any]:
    global _CANDIDATE_ID
    _CANDIDATE_ID += 1
    candidate_id = f"SEC-{category.replace('-', '_')}-{_CANDIDATE_ID:04d}"
    return {
        "id": candidate_id,
        "category": category,
        "severity_hint": severity,
        "confidence": confidence,
        "file": file,
        "line": line,
        "evidence": evidence,
        "recommended_review": (
            "Treat as a security candidate; confirm with code context before calling it a vulnerability."
        ),
        "verification_guidance": _verification_guidance(category),
        "false_positive_guidance": _false_positive_guidance(category),
        "requires_agent_review": requires_agent_review,
        "summary": description,
        "fingerprint": security_candidate_fingerprint(
            category=category,
            file=file,
            line=line,
            evidence=evidence,
        ),
    }


def _candidate_evidence(category: str, line: str) -> str:
    evidence = redact_secret_like_literals(
        line.strip(), force=category in _SECRET_EVIDENCE_CATEGORIES
    )
    return evidence[:240]


def _legacy_span_lines(
    spans: list[SecretAssignmentSpan], lines: list[str], pattern: str
) -> set[int]:
    return {span.start_line for span in spans if re.search(pattern, lines[span.start_line - 1])}


def _span_evidence(lines: list[str], start_line: int, end_line: int) -> str:
    return " ".join(line.strip() for line in lines[start_line - 1 : end_line] if line.strip())


def _additional_span_candidates(
    *,
    category: str,
    severity: str,
    description: str,
    relative_path: str,
    evidence_lines: list[str],
    source_lines: list[str],
    spans: list[SecretAssignmentSpan],
    legacy_lines: set[int],
) -> list[tuple[str, str, str, str, int, str, str]]:
    candidates: list[tuple[str, str, str, str, int, str, str]] = []
    for span in spans:
        if any(line in legacy_lines for line in range(span.start_line, span.end_line + 1)):
            continue
        evidence = _candidate_evidence(
            category,
            _span_evidence(evidence_lines, span.start_line, span.end_line),
        )
        confidence = _confidence_for_match(
            category,
            _span_evidence(source_lines, span.start_line, span.end_line),
        )
        candidates.append(
            (
                category,
                severity,
                confidence,
                relative_path,
                span.start_line,
                evidence,
                description,
            )
        )
    return candidates


def security_candidate_fingerprint(
    *,
    category: str,
    file: str,
    line: int,
    evidence: str,
) -> str:
    digest = hashlib.sha256(f"{category}|{file}|{line}|{evidence}".encode()).hexdigest()
    return f"sec-{digest[:16]}"


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for candidate in candidates:
        key = candidate["fingerprint"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _group_for_category(category: str) -> str:
    if category.startswith("secret") or category == "secrets-exposure":
        return "secrets"
    if category == "dangerous-sink":
        return "dangerous-sink"
    if "redirect" in category:
        return "redirect"
    if category in {"env-exposure", "secret-env-var"}:
        return "env-exposure"
    if category == "webhook-handler":
        return "webhook"
    if category == "expensive-api-abuse":
        return "expensive-api"
    return category


def _confidence_for_match(category: str, line: str) -> str:
    if category == "secrets-exposure" and re.search(
        r"(?i)(sk_live|sk_test|ghp_|AKIA|-----BEGIN)", line
    ):
        return "high"
    if category == "dangerous-sink":
        return "medium"
    return "low"


def _requires_agent_review(category: str) -> bool:
    return category in {
        "unsafe-redirect",
        "open-redirect",
        "webhook-handler",
        "expensive-api-abuse",
        "env-exposure",
    }


def _nearby_auth_signals(lines: list[str], line_number: int) -> bool:
    start = max(0, line_number - 8)
    end = min(len(lines), line_number + 8)
    window = "\n".join(lines[start:end]).lower()
    return any(
        term in window
        for term in (
            "auth",
            "authorize",
            "session",
            "middleware",
            "rate limit",
            "ratelimit",
            "requireuser",
            "getsession",
        )
    )


def _has_signature_verification(lines: list[str]) -> bool:
    text = "\n".join(lines[:120]).lower()
    return any(term in text for term in SIGNATURE_TERMS)


def _verification_guidance(category: str) -> str:
    guidance = {
        "secrets-exposure": "Rotate the secret if confirmed; replace with env-backed configuration.",
        "dangerous-sink": "Confirm input provenance; add validation or safer API.",
        "unsafe-redirect": "Add allowlist or same-origin validation for redirect targets.",
        "webhook-handler": "Verify HMAC/signature check occurs before side effects.",
        "env-exposure": "Move sensitive values to server-only env vars.",
        "expensive-api-abuse": "Require auth and rate limiting before expensive external calls.",
    }
    return guidance.get(category, "Review manually and record disposition in resolution ledger.")


def _false_positive_guidance(category: str) -> str:
    guidance = {
        "secrets-exposure": "Placeholder, test fixture, or example value not used in production.",
        "dangerous-sink": "Static command with no user-controlled fragments.",
        "unsafe-redirect": "Redirect target is validated against an allowlist elsewhere.",
        "webhook-handler": "Signature verification implemented in shared middleware.",
        "env-exposure": "Name is misleading but value is non-sensitive.",
        "expensive-api-abuse": "Route is authenticated and rate limited in middleware.",
    }
    return guidance.get(
        category,
        "Document why the candidate is safe and mark false-positive in the ledger.",
    )


def taxonomy_payload() -> dict[str, Any]:
    return {"categories": list(SECURITY_TAXONOMY_CATEGORIES)}
