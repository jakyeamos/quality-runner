"""Occurrence-aware BasedPyright strict-mode baselines.

Strict mode is a ratchet until its legacy diagnostics are resolved. This
module keeps that migration contract separate from the certified standard-mode
repository gate in ``pyproject.toml``.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

STRICT_BASELINE_SCHEMA = "quality-runner-basedpyright-strict-baseline-v0.1"
STRICT_DELTA_SCHEMA = "quality-runner-basedpyright-strict-delta-v0.1"


def normalize_diagnostics(payload: object, root: Path) -> list[dict[str, Any]]:
    """Normalize BasedPyright JSON diagnostics into stable occurrences.

    Line and character positions are retained as evidence but excluded from
    fingerprints, so line movement does not look like progress. Repeated
    identical diagnostics are assigned deterministic source-order ordinals.
    If a repeated group changes size, comparison blocks rather than guessing
    which occurrence was added or resolved.
    """

    if not isinstance(payload, dict):
        raise ValueError("BasedPyright output must be a JSON object")
    payload_map = cast(dict[str, object], payload)
    rows_value = payload_map.get("generalDiagnostics")
    if not isinstance(rows_value, list):
        raise ValueError("BasedPyright output is missing generalDiagnostics")

    root_path = root.resolve()
    grouped: defaultdict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw_value in cast(list[object], rows_value):
        if not isinstance(raw_value, dict):
            raise ValueError("BasedPyright diagnostic must be an object")
        raw = cast(dict[str, object], raw_value)
        file_value = raw.get("file")
        rule = raw.get("rule")
        message = raw.get("message")
        if not isinstance(file_value, str) or not file_value:
            raise ValueError("BasedPyright diagnostic is missing file, rule, or message")
        if not isinstance(rule, str) or not rule:
            raise ValueError("BasedPyright diagnostic is missing file, rule, or message")
        if not isinstance(message, str) or not message:
            raise ValueError("BasedPyright diagnostic is missing file, rule, or message")
        file_path = Path(file_value).resolve()
        try:
            relative_path = file_path.relative_to(root_path).as_posix()
        except ValueError as error:
            raise ValueError(f"diagnostic is outside repository root: {file_value}") from error
        group = (relative_path, rule, " ".join(message.split()))
        grouped[group].append(
            {
                "path": relative_path,
                "rule": rule,
                "message": group[2],
                "severity": str(raw.get("severity") or "unknown"),
                "start": _position(raw, "start"),
                "end": _position(raw, "end"),
            }
        )

    normalized: list[dict[str, Any]] = []
    for group, group_rows in sorted(grouped.items()):
        for ordinal, row in enumerate(sorted(group_rows, key=_diagnostic_sort_key)):
            identity = "\0".join((*group, str(ordinal)))
            normalized.append(
                {
                    **row,
                    "group": "\0".join(group),
                    "ordinal": ordinal,
                    "fingerprint": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                }
            )
    return sorted(normalized, key=lambda item: str(item["fingerprint"]))


def build_baseline(
    payload: object,
    *,
    root: Path,
    baseline_ref: str,
    config_path: str,
    config_sha256: str,
    repository: str | None = None,
    baseline_reason: str | None = None,
) -> dict[str, Any]:
    """Build a canonical, reviewable strict diagnostic baseline."""

    if not isinstance(payload, dict):
        raise ValueError("BasedPyright output must be a JSON object")
    payload_map = cast(dict[str, object], payload)
    summary_value = payload_map.get("summary")
    if not isinstance(summary_value, dict):
        raise ValueError("BasedPyright output is missing summary")
    summary = cast(dict[str, Any], summary_value)
    occurrences = normalize_diagnostics(payload_map, root)
    coverage = _coverage(summary, len(occurrences))
    return {
        "schema": STRICT_BASELINE_SCHEMA,
        "tool": "basedpyright",
        "tool_version": str(payload_map.get("version") or "unknown"),
        "repository": repository or root.resolve().name,
        "baseline_ref": baseline_ref,
        "config_path": config_path,
        "config_sha256": config_sha256,
        "baseline_reason": baseline_reason,
        "coverage": coverage,
        "legacy": {
            "state": "blocked" if occurrences else "clear",
            "occurrences": len(occurrences),
        },
        "summary": {
            "files_analyzed": summary.get("filesAnalyzed"),
            "errors": summary.get("errorCount"),
            "warnings": summary.get("warningCount"),
            "information": summary.get("informationCount"),
        },
        "occurrences": occurrences,
    }


def compare_baseline(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    expected_config_sha256: str | None = None,
    expected_tool_version: str | None = None,
) -> dict[str, Any]:
    """Compare two baselines without guessing through ambiguous groups."""

    blockers: list[str] = []
    if baseline.get("schema") != STRICT_BASELINE_SCHEMA:
        blockers.append("baseline schema is unsupported")
    if current.get("schema") != STRICT_BASELINE_SCHEMA:
        blockers.append("current scan schema is unsupported")
    if expected_config_sha256 and baseline.get("config_sha256") != expected_config_sha256:
        blockers.append("strict configuration changed; rebaseline is required")
    if expected_tool_version and baseline.get("tool_version") != expected_tool_version:
        blockers.append("BasedPyright version changed; rebaseline is required")
    if not _complete_coverage(baseline.get("coverage")):
        blockers.append("baseline coverage is not complete")
    if not _complete_coverage(current.get("coverage")):
        blockers.append("current strict scan coverage is not complete")

    baseline_rows = _rows_by_fingerprint(baseline.get("occurrences"))
    current_rows = _rows_by_fingerprint(current.get("occurrences"))
    baseline_groups = Counter(_group(row) for row in baseline_rows.values())
    current_groups = Counter(_group(row) for row in current_rows.values())
    ambiguous_groups = {
        group
        for group in set(baseline_groups) | set(current_groups)
        if baseline_groups[group]
        and current_groups[group]
        and max(baseline_groups[group], current_groups[group]) > 1
        and baseline_groups[group] != current_groups[group]
    }
    if ambiguous_groups:
        blockers.append("repeated diagnostic group changed size; occurrence matching is ambiguous")

    ambiguous = [
        row
        for row in [*baseline_rows.values(), *current_rows.values()]
        if _group(row) in ambiguous_groups
    ]
    ambiguous_keys = {row["fingerprint"] for row in ambiguous}
    baseline_keys = set(baseline_rows) - ambiguous_keys
    current_keys = set(current_rows) - ambiguous_keys
    new = [current_rows[key] for key in sorted(current_keys - baseline_keys)]
    persisted = [current_rows[key] for key in sorted(current_keys & baseline_keys)]
    resolved = [baseline_rows[key] for key in sorted(baseline_keys - current_keys)]
    state = (
        "blocked"
        if blockers or ambiguous
        else "failing"
        if new
        else "blocked"
        if persisted
        else "passed"
    )
    return {
        "schema": STRICT_DELTA_SCHEMA,
        "state": state,
        "new": new,
        "persisted": persisted,
        "resolved": resolved,
        "legacy_count": len(persisted),
        "unknown": ambiguous,
        "blockers": sorted(set(blockers)),
    }


def _coverage(summary: dict[str, Any], diagnostic_count: int) -> dict[str, Any]:
    files = summary.get("filesAnalyzed")
    counts = [summary.get(key) for key in ("errorCount", "warningCount", "informationCount")]
    expected = sum(
        value for value in counts if isinstance(value, int) and not isinstance(value, bool)
    )
    complete = (
        isinstance(files, int)
        and not isinstance(files, bool)
        and files > 0
        and expected == diagnostic_count
    )
    return {
        "state": "complete" if complete else "unknown",
        "files_analyzed": files,
        "diagnostics_reported": diagnostic_count,
    }


def _complete_coverage(value: object) -> bool:
    return isinstance(value, dict) and value.get("state") == "complete"


def _position(raw: dict[str, object], name: str) -> dict[str, int]:
    value = raw.get("range", {})
    range_map = cast(dict[str, object], value) if isinstance(value, dict) else {}
    position = range_map.get(name)
    if not isinstance(position, dict):
        raise ValueError(f"BasedPyright diagnostic is missing range.{name}")
    position_map = cast(dict[str, object], position)
    line = position_map.get("line")
    character = position_map.get("character")
    if not isinstance(line, int) or isinstance(line, bool):
        raise ValueError(f"BasedPyright range.{name} must contain integer line and character")
    if not isinstance(character, int) or isinstance(character, bool):
        raise ValueError(f"BasedPyright range.{name} must contain integer line and character")
    return {"line": line, "character": character}


def _diagnostic_sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, str]:
    start = item["start"]
    end = item["end"]
    return (
        int(start["line"]),
        int(start["character"]),
        int(end["line"]),
        int(end["character"]),
        str(item["severity"]),
    )


def _rows_by_fingerprint(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    rows: dict[str, dict[str, Any]] = {}
    for raw_item in cast(list[object], value):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, Any], raw_item)
        fingerprint = item.get("fingerprint")
        if isinstance(fingerprint, str):
            rows[fingerprint] = item
    return rows


def _group(row: dict[str, Any]) -> str:
    return str(row.get("group") or "")
