from __future__ import annotations

import re

REDACTED_LITERAL = "<redacted>"
SECRET_ASSIGNMENT_PATTERN = (
    r"(?i)(api[_-]?key|secret|password|token|private[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
)
SECRET_FALLBACK_PATTERN = r"(?i)(?:\|\||\?\?)\s*['\"][^'\"]{12,}['\"]"
SECRET_LOG_PATTERN = (
    r"(?i)(?:console\.|logger\.|print\(|logging\.).*(?:password|secret|token|api[_-]?key)"
)

_SECRET_EVIDENCE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        SECRET_ASSIGNMENT_PATTERN,
        SECRET_FALLBACK_PATTERN,
        SECRET_LOG_PATTERN,
    )
)
_QUOTED_LITERAL = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`""")


def redact_secret_like_literals(value: str, *, force: bool = False) -> str:
    if not force and not any(pattern.search(value) for pattern in _SECRET_EVIDENCE_PATTERNS):
        return value
    return _QUOTED_LITERAL.sub(f'"{REDACTED_LITERAL}"', value)
