from __future__ import annotations

from quality_runner.actionability import actionability_for_finding
from quality_runner.security.audit import security_audit_findings
from quality_runner.security.candidates import scan_security_candidates
from quality_runner.security.disposition import classify_security_candidate


def test_env_reads_are_triageable_without_becoming_author_blockers() -> None:
    disposition = classify_security_candidate(
        category="secret-env-var",
        confidence="low",
        file="src/server/config.ts",
        evidence="const value = process.env.API_TOKEN;",
    )

    assert disposition["disposition_class"] == "triage"
    assert disposition["disposition_required"] is False
    assert (
        actionability_for_finding(
            {
                "category": "security:secret-env-var",
                "severity": "blocker",
                **disposition,
            }
        )[0]
        == "needs-triage"
    )


def test_high_signal_candidate_requires_owner_review() -> None:
    disposition = classify_security_candidate(
        category="secrets-exposure",
        confidence="high",
        file="src/server/config.ts",
        evidence='const key = "<redacted>";',
    )

    assert disposition["disposition_class"] == "human-review"
    assert disposition["disposition_required"] is True
    assert (
        actionability_for_finding(
            {
                "category": "security:secrets-exposure",
                "severity": "blocker",
                **disposition,
            }
        )[0]
        == "needs-author-decision"
    )


def test_security_audit_preserves_disposition_metadata() -> None:
    findings = security_audit_findings(
        {
            "settings": {"enabled": True},
            "candidates": [
                {
                    "id": "SEC-secret_env_var-0001",
                    "category": "secret-env-var",
                    "severity_hint": "medium",
                    "confidence": "low",
                    "file": "src/server/config.ts",
                    "line": 4,
                    "evidence": "process.env.API_TOKEN",
                    "verification_guidance": "Review usage.",
                    "disposition_class": "triage",
                    "disposition_group": "security:secret-env-var:source-context",
                    "disposition_required": False,
                    "owner_role": "platform-security",
                    "disposition_rationale": "Group similar candidates.",
                }
            ],
        }
    )

    assert findings[0]["disposition_class"] == "triage"
    assert findings[0]["owner_role"] == "platform-security"
    assert findings[0]["disposition_group"].endswith("source-context")


def test_scan_assigns_group_and_owner_role() -> None:
    candidates = scan_security_candidates(
        scanned_files=[
            {
                "path": "tests/config.test.ts",
                "lines": ["const token = process.env.API_TOKEN;"],
            }
        ],
        disabled_groups=[],
        surfaces={},
        owner_role="platform-security",
    )

    candidate = next(item for item in candidates if item["category"] == "secret-env-var")
    assert candidate["owner_role"] == "platform-security"
    assert candidate["disposition_class"] == "bulk-review-eligible"
    assert candidate["disposition_required"] is False
