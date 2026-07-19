from __future__ import annotations

import re
from typing import Any

DISPOSITION_CLASSES = {"human-review", "triage", "bulk-review-eligible"}

_SAFE_PATH_MARKERS = {"test", "tests", "fixture", "fixtures", "example", "examples", "seed", "uat"}
_SAFE_LITERAL_MARKERS = ("dummy", "example", "fake", "fixture", "placeholder", "test-", "test_")
_SENSITIVE_RUNTIME_MARKERS = ("otp", "totp", "token", "password", "credential")


def classify_security_candidate(
    *,
    category: str,
    confidence: str,
    file: str,
    evidence: str,
    owner_role: str = "security-maintainer",
) -> dict[str, Any]:
    """Route heuristic candidates without treating every match as a blocker."""

    lowered_category = category.lower()
    lowered_evidence = evidence.lower()
    safe_context = _safe_context(file, lowered_evidence)
    high_confidence = confidence.lower() == "high"
    human_review = (
        lowered_category in {"env-exposure", "dangerous-sink", "unsafe-redirect", "open-redirect"}
        or high_confidence
        or (
            lowered_category == "secret-in-log"
            and not safe_context
            and any(marker in lowered_evidence for marker in _SENSITIVE_RUNTIME_MARKERS)
        )
    )
    if human_review:
        disposition_class = "human-review"
        rationale = "High-signal security candidates require a named security decision."
    elif safe_context:
        disposition_class = "bulk-review-eligible"
        rationale = "Test, fixture, example, or development context is eligible for grouped review."
    else:
        disposition_class = "triage"
        rationale = "Low-confidence heuristic candidate should be triaged in a bounded family, not block the phase."

    return {
        "disposition_class": disposition_class,
        "disposition_group": f"security:{lowered_category}:{'safe-context' if safe_context else 'source-context'}",
        "disposition_required": disposition_class == "human-review",
        "owner_role": owner_role,
        "disposition_rationale": rationale,
    }


def _safe_context(file: str, evidence: str) -> bool:
    path_parts = set(re.split(r"[/_.-]+", file.lower().replace("\\", "/")))
    return bool(path_parts.intersection(_SAFE_PATH_MARKERS)) or any(
        marker in evidence for marker in _SAFE_LITERAL_MARKERS
    )
