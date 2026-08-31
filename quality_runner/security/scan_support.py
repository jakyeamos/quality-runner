from __future__ import annotations


def string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


_string_or_none = string_or_none
