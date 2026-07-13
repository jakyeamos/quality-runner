from __future__ import annotations

import re
import unicodedata

_SECRET_ASSIGNMENT_NAME = re.compile(
    r"""(?x)\b(?:
    (?i:api[_-]?key|secret|password|token|private[_-]?key)
    (?:(?:[_-][A-Za-z0-9]+)|(?:[A-Z][A-Za-z0-9]*))*
    | [A-Za-z0-9]+(?:_[A-Za-z0-9]+)*(?i:_key|_token|_secret|_password)(?:_[A-Za-z0-9]+)*
    )\b"""
)
_CAMEL_SECRET_ASSIGNMENT_NAME = re.compile(
    r"\b[A-Za-z][A-Za-z0-9]*(?:Key|Token|Secret|Password)(?:[A-Z][A-Za-z0-9]*)*\b"
)
_IDENTIFIER_ESCAPE = r"\\(?:u(?:[0-9A-Fa-f]{4}|\{[0-9A-Fa-f]{1,6}\})|x[0-9A-Fa-f]{2}|[0-7]{1,3}|.)"
_IDENTIFIER = re.compile(rf"(?<![\w$\\])(?:[\w$]|{_IDENTIFIER_ESCAPE})+(?![\w$])")
_KEY_ESCAPE = re.compile(
    r"\\(?:u(?:([0-9A-Fa-f]{4})|\{([0-9A-Fa-f]{1,6})\})|x([0-9A-Fa-f]{2})|([0-7]{1,3})|(.))"
)


def source_secret_name_matches(value: str) -> list[tuple[int, int]]:
    matches = {
        (match.start(), match.end())
        for pattern in (_SECRET_ASSIGNMENT_NAME, _CAMEL_SECRET_ASSIGNMENT_NAME)
        for match in pattern.finditer(value)
    }
    matches.update(
        (match.start(), match.end())
        for match in _IDENTIFIER.finditer(value)
        if is_sensitive_name(decode_escaped_name(match.group(0)))
    )
    return sorted(matches)


def decode_escaped_name(value: str) -> str:
    escapes = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "'": "'", '"': '"'}

    def replace(match: re.Match[str]) -> str:
        four_digit, braced, hex_value, octal_value, character = match.groups()
        if four_digit is not None:
            return chr(int(four_digit, 16))
        if braced is not None:
            return chr(int(braced, 16))
        if hex_value is not None:
            return chr(int(hex_value, 16))
        if octal_value is not None:
            return chr(int(octal_value, 8))
        return escapes.get(character, character)

    return _KEY_ESCAPE.sub(replace, value)


def is_sensitive_name(value: str) -> bool:
    normalized = unicodedata.normalize("NFKC", value)
    return _SECRET_ASSIGNMENT_NAME.fullmatch(normalized) is not None or (
        _CAMEL_SECRET_ASSIGNMENT_NAME.fullmatch(normalized) is not None
    )
