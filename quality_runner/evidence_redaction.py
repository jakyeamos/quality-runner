from __future__ import annotations

import re
from collections.abc import Sequence

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

_SECRET_EVIDENCE_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        SECRET_ASSIGNMENT_PATTERN,
        SECRET_FALLBACK_PATTERN,
        SECRET_LOG_PATTERN,
    )
)
_QUOTED_LITERAL = re.compile(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`""")
_SECRET_ASSIGNMENT_NAME = re.compile(
    r"""(?ix)\b(?:
    api[_-]?key
    | secret
    | password
    | token
    | private[_-]?key
    | [a-z0-9_]+(?:_key|_token|_secret|_password)
    )\b"""
)
_CAMEL_SECRET_ASSIGNMENT_NAME = re.compile(r"\b[A-Za-z0-9_]+(?:Key|Token|Secret|Password)\b")
_QUOTE_START = re.compile(r"""["'`]""")


def redact_secret_like_literals(value: str, *, force: bool = False) -> str:
    if not force and not any(pattern.search(value) for pattern in _SECRET_EVIDENCE_PATTERNS):
        return value
    return _QUOTED_LITERAL.sub(f'"{REDACTED_LITERAL}"', value)


def redact_secret_like_source_lines(lines: Sequence[str]) -> list[str]:
    pending_secret_value = False
    open_secret_quote: str | None = None
    redacted_lines: list[str] = []

    for line in lines:
        redacted_line = redact_secret_like_literals(
            line,
            force=bool(_secret_assignment_right_hand_sides(line)),
        )
        if pending_secret_value:
            redacted_line, pending_secret_value, open_secret_quote = _redact_pending_secret_value(
                redacted_line, open_secret_quote
            )
        starts_continuation, opening_secret_quote = _starts_secret_assignment_continuation(line)
        if starts_continuation:
            if opening_secret_quote is not None:
                redacted_line = _redact_unclosed_secret_assignment(
                    redacted_line, opening_secret_quote
                )
            pending_secret_value = True
            open_secret_quote = opening_secret_quote
        redacted_lines.append(redacted_line)

    return redacted_lines


def _redact_pending_secret_value(
    value: str,
    open_quote: str | None,
) -> tuple[str, bool, str | None]:
    if open_quote is not None:
        closing_quote = _closing_quote_index(value, open_quote, 0)
        if closing_quote is None:
            return f'"{REDACTED_LITERAL}"', True, open_quote
        suffix = redact_secret_like_literals(value[closing_quote + 1 :], force=True)
        return (
            f'"{REDACTED_LITERAL}"{suffix}',
            _secret_expression_continues(suffix, allow_blank=False),
            None,
        )

    quote_start = _QUOTE_START.search(value)
    if quote_start is None:
        return value, _secret_expression_continues(value, allow_blank=True), None
    quote = quote_start.group(0)
    closing_quote = _closing_quote_index(value, quote, quote_start.start())
    if closing_quote is None:
        return f'{value[: quote_start.start()]}"{REDACTED_LITERAL}"', True, quote
    suffix = redact_secret_like_literals(value[closing_quote + 1 :], force=True)
    return (
        f'{value[: quote_start.start()]}"{REDACTED_LITERAL}"{suffix}',
        _secret_expression_continues(suffix, allow_blank=False),
        None,
    )


def _redact_unclosed_secret_assignment(value: str, quote: str) -> str:
    quote_start = value.rfind(quote)
    if quote_start < 0:
        return value
    return f'{value[:quote_start]}"{REDACTED_LITERAL}"'


def _starts_secret_assignment_continuation(value: str) -> tuple[bool, str | None]:
    for right_hand_side in _secret_assignment_right_hand_sides(value):
        if not right_hand_side or right_hand_side.startswith(("(", "[", "{", "//", "/*")):
            return True, None
        opening_quote = right_hand_side[0]
        if (
            opening_quote in {"'", '"', "`"}
            and _closing_quote_index(right_hand_side, opening_quote, 0) is None
        ):
            return True, opening_quote
        if _secret_expression_continues(right_hand_side, allow_blank=False):
            return True, None
    return False, None


def _secret_assignment_right_hand_sides(value: str) -> list[str]:
    secret_names = sorted(
        [
            *_SECRET_ASSIGNMENT_NAME.finditer(value),
            *_CAMEL_SECRET_ASSIGNMENT_NAME.finditer(value),
        ],
        key=lambda item: item.start(),
    )
    right_hand_sides: list[str] = []
    for secret_name in secret_names:
        remainder = value[secret_name.end() :]
        statement_end = remainder.find(";")
        if statement_end >= 0:
            remainder = remainder[:statement_end]
        equals = remainder.find("=")
        colon = remainder.find(":")
        assignment = equals if equals >= 0 else colon
        if assignment >= 0:
            right_hand_sides.append(remainder[assignment + 1 :].strip())
    return right_hand_sides


def _secret_expression_continues(value: str, *, allow_blank: bool) -> bool:
    expression = value.split("//", maxsplit=1)[0].rstrip()
    if not expression:
        return allow_blank
    if ";" in expression:
        return False
    return expression.endswith(("+", ",", "&&", "||", "??", "?", ":", ".", "(", "[", "{"))


def _closing_quote_index(value: str, quote: str, start: int) -> int | None:
    escaped = False
    for index in range(start + 1, len(value)):
        character = value[index]
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == quote:
            return index
    return None
