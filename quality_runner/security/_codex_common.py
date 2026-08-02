"""Shared deterministic helpers for Codex Security evidence adapters."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from quality_runner.schema_constants import CODEX_SECURITY_RESULT_SCHEMA

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_PATH_KEYS = ("file", "path", "uri", "artifact", "filename", "file_path", "filePath")
_ID_KEYS = ("finding_id", "provider_finding_id", "alert_id", "uuid", "id")
_FINGERPRINT_KEYS = ("fingerprint", "stable_id", "stable_key", "match_key")
_RULE_KEYS = ("rule_id", "ruleId", "check_id", "category", "criterion_id", "type")
_SUMMARY_KEYS = ("summary", "title", "message", "description", "detail", "name")
_SEVERITY_KEYS = ("severity", "level", "severity_hint", "priority", "risk")
_STATUS_KEYS = ("status", "state", "resolution", "disposition")

# Public adapter aliases keep the shared evidence contract consumable without
# exposing private implementation names across security provider modules.
HEX_64 = _HEX_64
ID_KEYS = _ID_KEYS
FINGERPRINT_KEYS = _FINGERPRINT_KEYS
RULE_KEYS = _RULE_KEYS
SUMMARY_KEYS = _SUMMARY_KEYS
SEVERITY_KEYS = _SEVERITY_KEYS
STATUS_KEYS = _STATUS_KEYS


def canonical_json(value: Any) -> str:
    """Return the one JSON representation used for all adapter hashes."""

    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(value: Any, *, exclude: Sequence[str] = ()) -> str:
    """Hash a JSON value, excluding named top-level hash fields."""

    value_map = _mapping(value)
    if value_map is not None:
        excluded = set(exclude)
        value = {str(key): item for key, item in value_map.items() if str(key) not in excluded}
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_codex_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from a local evidence path."""

    resolved = path.expanduser().resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    payload_map = _mapping(payload)
    if payload_map is None:
        raise ValueError(f"JSON object required: {resolved}")
    return dict(payload_map)


def write_codex_json(path: Path, payload: Mapping[str, Any]) -> Path:
    """Write a deterministic JSON artifact and return its resolved path."""

    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return resolved


def _normalize_coverage(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        raw = {"status": raw}
    raw = _mapping(raw) or {}
    status_raw = _normal_key(str(raw.get("status", "unknown")))
    explicit_complete = raw.get("complete")
    complete = status_raw in {"complete", "completed", "full", "covered"}
    if explicit_complete is not None:
        complete = bool(explicit_complete) and status_raw not in {"partial", "incomplete"}
    scanned = _path_list(
        raw.get("scanned_paths")
        or raw.get("scanned_files")
        or raw.get("files_scanned")
        or raw.get("covered_paths")
        or raw.get("paths")
    )
    expected = _path_list(
        raw.get("expected_paths")
        or raw.get("expected_files")
        or raw.get("files_expected")
        or raw.get("scope_paths")
        or raw.get("all_paths")
    )
    if scanned and expected and set(scanned) == set(expected) and explicit_complete is not False:
        complete = True
        status_raw = "complete"
    files_scanned = _first_int(
        raw,
        ("files_scanned", "scanned_files_count", "analyzed_files", "files_analyzed"),
    )
    files_expected = _first_int(
        raw,
        ("files_expected", "expected_files_count", "total_files", "files_in_scope"),
    )
    if (
        isinstance(files_scanned, int)
        and isinstance(files_expected, int)
        and files_scanned >= 0
        and files_scanned == files_expected
        and explicit_complete is not False
    ):
        complete = True
        status_raw = "complete"
    if complete:
        status = "complete"
    elif status_raw in {"partial", "incomplete", "blocked", "unavailable"}:
        status = "partial"
    else:
        status = "unknown"
    follow_up = raw.get("follow_up")
    follow_up_complete = complete
    follow_up_map = _mapping(follow_up)
    if follow_up_map is not None:
        follow_up_complete = bool(
            follow_up_map.get(
                "complete",
                follow_up_map.get("coverage_complete", follow_up_map.get("status") == "complete"),
            )
        )
    elif follow_up is not None:
        follow_up_complete = bool(follow_up)
    if raw.get("follow_up_complete") is not None:
        follow_up_complete = bool(raw["follow_up_complete"])
    scope = raw.get("scope", "unknown")
    scope_map = _mapping(scope)
    if scope_map is not None:
        scope = scope_map.get("type") or scope_map.get("kind") or scope_map.get("name") or "unknown"
    result: dict[str, Any] = {
        "status": status,
        "complete": complete,
        "follow_up_complete": follow_up_complete,
        "scope": _normal_key(str(scope)) or "unknown",
        "scanned_paths": scanned,
        "expected_paths": expected,
        "covered_match_keys": sorted(
            str(item) for item in cast(list[Any], raw.get("covered_match_keys", []) or [])
        ),
    }
    follow_up_of = raw.get("follow_up_of")
    if follow_up_of is not None:
        result["follow_up_of"] = str(follow_up_of)
    return result


def _raw_coverage(raw: Mapping[str, Any]) -> Any:
    if raw.get("coverage") is not None:
        return raw["coverage"]
    scan = _mapping(raw.get("scan"))
    if scan is not None and scan.get("coverage") is not None:
        return scan["coverage"]
    if raw.get("coverage_summary") is not None:
        return raw["coverage_summary"]
    if raw.get("follow_up_coverage") is not None:
        return raw["follow_up_coverage"]
    if raw.get("coverage_complete") is not None:
        return {
            "complete": raw["coverage_complete"],
            "scope": raw.get("coverage_scope", raw.get("scope", "unknown")),
        }
    return None


def _normalize_source(raw: Mapping[str, Any]) -> dict[str, Any]:
    source = raw.get("source")
    source_map = _mapping(source)
    if source_map is not None:
        descriptor: dict[str, Any] = {
            str(key): value for key, value in source_map.items() if value is not None
        }
    elif source is not None:
        descriptor = {"report": str(source)}
    else:
        descriptor = {}
    descriptor["provider"] = "codex-security"
    descriptor.setdefault("kind", "security-report")
    return descriptor


def _normalize_repository(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = raw.get("repository") or raw.get("repo")
    value_map = _mapping(value)
    if value_map is not None:
        return {str(key): item for key, item in value_map.items() if item is not None}
    if value is not None:
        return {"root": str(value)}
    return {}


def _normalize_revision(raw: Mapping[str, Any]) -> dict[str, Any]:
    value = raw.get("revision")
    value_map = _mapping(value)
    if value_map is not None:
        return {str(key): item for key, item in value_map.items() if item is not None}
    revision: dict[str, Any] = {}
    commit = _first_text(raw, ("commit_sha", "commit", "sha", "revision"))
    ref = _first_text(raw, ("ref", "branch", "head"))
    if commit:
        revision["commit"] = commit
    if ref:
        revision["ref"] = ref
    return revision


def _normalize_locations(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_locations: Any = source.get("locations") or source.get("location") or []
    if isinstance(raw_locations, (str, Mapping)):
        raw_locations = [raw_locations]
    if not isinstance(raw_locations, list):
        raw_locations = []
    raw_locations = cast(list[Any], raw_locations)
    normalized: list[dict[str, Any]] = []
    for raw_location in raw_locations:
        location = _location_item(raw_location)
        if location:
            normalized.append(location)
    normalized.sort(key=lambda item: (str(item.get("file", "")), int(item.get("line", 0))))
    return normalized


def _location_item(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        path = _normalize_path(value)
        return {"file": path} if path else {}
    value_map = _mapping(value)
    if value_map is None:
        return {}
    value = value_map
    physical = _mapping(value.get("physicalLocation"))
    if physical is not None:
        return _location_item(physical)
    artifact = value.get("artifactLocation")
    path = _first_text(value, _PATH_KEYS)
    artifact_map = _mapping(artifact)
    if not path and artifact_map is not None:
        path = _first_text(artifact_map, ("uri", "uriBaseId", "path"))
    region = value.get("region")
    region = _mapping(region) or {}
    line_value = (
        value.get("line")
        or value.get("start_line")
        or value.get("line_start")
        or region.get("startLine")
    )
    location: dict[str, Any] = {}
    if path:
        location["file"] = _normalize_path(path)
    if isinstance(line_value, int) and line_value > 0:
        location["line"] = line_value
    end_line = value.get("end_line") or value.get("line_end") or region.get("endLine")
    if isinstance(end_line, int) and end_line > 0:
        location["end_line"] = end_line
    return location


def _evidence_items(
    source: Mapping[str, Any], summary: str, locations: Sequence[Mapping[str, Any]]
) -> list[Any]:
    value = source.get("evidence") or source.get("validation_evidence") or source.get("validation")
    items: list[Any] = []
    if isinstance(value, str):
        items.append(value)
    elif value_map := _mapping(value):
        items.append(dict(value_map))
    elif isinstance(value, list):
        items.extend(
            item
            for item in cast(list[Any], value)
            if isinstance(item, str) or _mapping(item) is not None
        )
    for key in ("attack_path", "remediation", "recommendation", "code_snippet"):
        item = source.get(key)
        if (isinstance(item, str) or _mapping(item) is not None) and item not in items:
            items.append(item)
    if not items:
        items.append({"kind": "codex-finding", "summary": summary})
    if locations and not any(
        (item_map := _mapping(item)) is not None and item_map.get("file") for item in items
    ):
        items.extend({"kind": "location", **location} for location in locations)
    return items


def _metadata(source: Mapping[str, Any]) -> dict[str, Any]:
    value = source.get("metadata") or source.get("properties")
    value_map = _mapping(value)
    if value_map is None:
        return {}
    return {str(key): item for key, item in value_map.items() if item is not None}


def _quality_level(source: Mapping[str, Any]) -> str:
    raw = _normal_key(_first_text(source, _SEVERITY_KEYS) or "warning")
    if raw in {"pass", "info", "warning", "blocker", "error", "critical"}:
        return raw
    if raw in {"high", "urgent", "severe"}:
        return "blocker"
    if raw in {"medium", "moderate"}:
        return "warning"
    if raw in {"low", "minor", "note"}:
        return "info"
    return "warning"


def _evidence_summary(
    findings: Sequence[Mapping[str, Any]], coverage: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "finding_count": len(findings),
        "blocking_count": sum(1 for finding in findings if finding.get("blocking") is True),
        "warning_count": sum(1 for finding in findings if finding.get("level") == "warning"),
        "coverage_status": coverage["status"],
        "coverage_complete": coverage["complete"],
    }


def _validation_result(
    payload: Any, *, errors: Sequence[str], warnings: Sequence[str] = ()
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema": CODEX_SECURITY_RESULT_SCHEMA,
        "operation": "validate",
        "status": "validated" if not errors else "rejected",
        "passed": not errors,
        "implementation_allowed": False,
        "errors": sorted(str(error) for error in errors),
        "warnings": sorted(str(warning) for warning in warnings),
    }
    payload_map = _mapping(payload)
    if payload_map is not None:
        result["input_schema"] = payload_map.get("schema")
        for key in ("source_hash", "evidence_hash", "comparison_hash", "handoff_hash"):
            if isinstance(payload_map.get(key), str):
                result[key] = payload_map[key]
    return result


def _validate_coverage(value: Any, errors: list[str]) -> None:
    value_map = _mapping(value)
    if value_map is None:
        errors.append("Codex evidence coverage must be an object")
        return
    if value_map.get("status") not in {"complete", "partial", "unknown"}:
        errors.append("Codex evidence coverage.status is invalid")
    if not isinstance(value_map.get("complete"), bool):
        errors.append("Codex evidence coverage.complete must be boolean")
    if not isinstance(value_map.get("follow_up_complete"), bool):
        errors.append("Codex evidence coverage.follow_up_complete must be boolean")
    for field in ("scanned_paths", "expected_paths", "covered_match_keys"):
        field_value = value_map.get(field)
        if not isinstance(field_value, list) or not all(
            isinstance(item, str) for item in cast(list[Any], field_value)
        ):
            errors.append(f"Codex evidence coverage.{field} must be a string list")


def _first_text(source: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = source.get(key)
        if value is None or isinstance(value, (Mapping, list, tuple)):
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _first_int(source: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
    return None


def _path_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return sorted(
        {_normalize_path(str(item)) for item in cast(list[Any], value) if str(item).strip()}
    )


def _normalize_path(value: str) -> str:
    path = value.strip().replace("\\", "/")
    if path.startswith("file://"):
        path = path[7:]
    while path.startswith("./"):
        path = path[2:]
    return path


def _normal_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _normal_key(value: str) -> str:
    return _normal_text(value).replace(" ", "_")


def _drop_none_values(value: Any) -> Any:
    value_map = _mapping(value)
    if value_map is not None:
        return {key: _drop_none_values(item) for key, item in value_map.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none_values(item) for item in cast(list[Any], value)]
    return value


def _mapping(value: Any) -> Mapping[str, Any] | None:
    """Narrow JSON-like mappings at adapter boundaries without changing values."""

    if not isinstance(value, Mapping):
        return None
    return cast(Mapping[str, Any], value)


# Public aliases are the stable import surface for provider adapters.
drop_none_values = _drop_none_values
evidence_items = _evidence_items
evidence_summary = _evidence_summary
first_text = _first_text
metadata = _metadata
normal_key = _normal_key
normal_text = _normal_text
normalize_coverage = _normalize_coverage
normalize_locations = _normalize_locations
normalize_repository = _normalize_repository
normalize_revision = _normalize_revision
normalize_source = _normalize_source
normalize_path = _normalize_path
quality_level = _quality_level
raw_coverage = _raw_coverage
validate_coverage = _validate_coverage
validation_result = _validation_result
