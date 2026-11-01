from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any, TypeGuard

from quality_runner.artifacts import safe_child_file
from quality_runner.review_response_files import read_regular_text_file

PREFIX = "quality-runner-model-audit-"
MAX_JSON_BYTES = 4_000_000


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _is_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, dict)


def _is_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def object_value(value: object, label: str) -> dict[str, Any]:
    if not _is_mapping(value):
        raise ValueError(f"{label} must be an object")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{label} keys must be strings")
        result[key] = item
    return result


def array_value(value: object, label: str, *, minimum: int = 0, maximum: int = 256) -> list[object]:
    if not _is_list(value) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{label} requires {minimum} to {maximum} entries")
    return value


def text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 16_384:
        raise ValueError(f"{label} must be nonempty bounded text")
    return value


def strings(value: object, label: str) -> list[str]:
    return [text(item, label) for item in array_value(value, label)]


def exact_keys(value: Mapping[str, object], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ValueError(f"{label} requires exactly: {', '.join(sorted(keys))}")


def relative_path(value: object, *, root_allowed: bool = False) -> str:
    name = text(value, "path")
    path = PurePosixPath(name)
    if name == "." and root_allowed:
        return name
    if path.is_absolute() or ".." in path.parts or not path.parts or str(path) != name:
        raise ValueError("path must be a normalized relative path without traversal")
    if path.parts[0] in {".git", ".quality-runner"}:
        raise ValueError("audit inputs cannot include Git internals or generated QR evidence")
    return name


def validate_profile(raw: object) -> dict[str, Any]:
    value = object_value(raw, "profile")
    exact_keys(
        value,
        {
            "schema",
            "id",
            "revision",
            "purpose",
            "constraints",
            "criteria",
            "include_paths",
            "exclude_paths",
        },
        "profile",
    )
    if value["schema"] != PREFIX + "profile/v1":
        raise ValueError("unsupported model audit profile schema")
    for key in ("id", "revision", "purpose"):
        text(value[key], key)
    strings(value["constraints"], "constraints")
    criteria = array_value(value["criteria"], "criteria", minimum=1, maximum=64)
    identifiers: set[str] = set()
    for raw_criterion in criteria:
        criterion = object_value(raw_criterion, "criterion")
        exact_keys(criterion, {"id", "prompt"}, "criterion")
        identifier = text(criterion["id"], "criterion id")
        text(criterion["prompt"], "criterion prompt")
        if identifier in identifiers:
            raise ValueError("duplicate criterion id")
        identifiers.add(identifier)
    for key in ("include_paths", "exclude_paths"):
        for path in strings(value[key], key):
            relative_path(path, root_allowed=True)
    if not value["include_paths"]:
        raise ValueError("include_paths cannot be empty")
    return value


def validate_reviewer(raw: object) -> dict[str, Any]:
    value = object_value(raw, "reviewer")
    exact_keys(
        value,
        {"reviewer_id", "model", "provider", "effort", "harness", "tools", "budget"},
        "reviewer",
    )
    for key in ("reviewer_id", "model", "provider", "effort", "harness"):
        text(value[key], key)
    strings(value["tools"], "tools")
    budget = object_value(value["budget"], "budget")
    exact_keys(budget, {"seconds", "max_findings"}, "budget")
    for key, maximum in (("seconds", 86_400), ("max_findings", 256)):
        if type(budget[key]) is not int or not 1 <= budget[key] <= maximum:
            raise ValueError(f"budget {key} must be between 1 and {maximum}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    return object_value(
        json.loads(read_regular_text_file(path, maximum_bytes=MAX_JSON_BYTES)), str(path)
    )


def write_once(directory: Path, name: str, value: object) -> Path:
    path = safe_child_file(directory, name)
    data = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("model audit artifact exceeds size limit")
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
    return path
