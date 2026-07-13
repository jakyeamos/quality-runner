from __future__ import annotations

REDACTED_LITERAL = "<redacted>"
SECRET_ASSIGNMENT_PATTERN = (
    r"(?i)(api[_-]?key|secret|password|token|private[_-]?key)\b"
    r"(?:\s|/\*.*?\*/)*(?::\s*[^=;'\"`\n]*?=|=|:)\s*"
    r"[^;\n]*?['\"`][^'\"`]{8,}['\"`]"
)
SECRET_FALLBACK_PATTERN = r"(?i)(?:\|\||\?\?)\s*['\"`][^'\"`]{12,}['\"`]"
SECRET_LOG_PATTERN = (
    r"(?i)(?:console\.|logger\.|print\(|logging\.).*(?:password|secret|token|api[_-]?key)"
)
