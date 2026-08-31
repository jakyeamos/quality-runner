from __future__ import annotations

from collections.abc import Mapping
from typing import cast


def mapping_equals(value: object, key: str, expected: object) -> bool:
    mapped = cast(Mapping[str, object], value) if isinstance(value, Mapping) else None
    return mapped is not None and mapped.get(key) == expected


_mapping_equals = mapping_equals
