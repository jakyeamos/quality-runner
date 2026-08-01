from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _cue_type(value: object) -> str | None:
    value = (
        value
        if isinstance(value, str)
        else cast(Mapping[str, object], value).get("type")
        if isinstance(value, Mapping)
        else None
    )
    return value.strip().lower() or None if isinstance(value, str) else None


def _stable(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[Any], value) if isinstance(item, str)]


mapping = _mapping
text = _text
cue_type = _cue_type
stable = _stable
strings = _strings
