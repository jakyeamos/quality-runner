from __future__ import annotations

from collections.abc import Sequence

from quality_runner.evidence_redaction_contract import (
    REDACTED_LITERAL,
    SECRET_ASSIGNMENT_PATTERN,
    SECRET_FALLBACK_PATTERN,
    SECRET_LOG_PATTERN,
)
from quality_runner.source_evidence_redaction import (
    SecretAssignmentSpan,
    SecretSourceAnalysis,
    analyze_secret_like_source_lines,
    redact_source_literals,
)

__all__ = [
    "REDACTED_LITERAL",
    "SECRET_ASSIGNMENT_PATTERN",
    "SECRET_FALLBACK_PATTERN",
    "SECRET_LOG_PATTERN",
    "SecretAssignmentSpan",
    "SecretSourceAnalysis",
    "analyze_secret_like_source_lines",
    "redact_secret_like_literals",
    "redact_secret_like_source_lines",
]


def redact_secret_like_literals(value: str, *, force: bool = False) -> str:
    return redact_source_literals(value, force=force)


def redact_secret_like_source_lines(lines: Sequence[str]) -> list[str]:
    return analyze_secret_like_source_lines(lines).lines
