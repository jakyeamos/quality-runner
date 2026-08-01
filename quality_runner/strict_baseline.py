"""Occurrence-aware BasedPyright strict-mode baselines.

Strict mode is an advisory burndown until its evidence is strong enough to be
promoted.  This module deliberately keeps the baseline contract separate from
the certified repository gate in ``pyproject.toml``.
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

    The fingerprint intentionally excludes line numbers so line movement does
    not look like progress.  Repeated identical diagnostics are disambiguated
    by their deterministic source order; if a repeated group changes size,
    comparison blocks rather than guessing which occurrence changed.
    """

    if not isinstance(payload, dict):
        raise ValueError("BasedPyright output must be a JSON object")
    payload_map = cast(dict[str, object], payload)
    rows_value = payload_map.get("generalDiagnostics")
    if not isinstance(rows_value, list):
        raise ValueError("BasedPyright output is missing generalDiagnostics")
    rows = cast(list[object], rows_value)

    root_path = root.resolve()
    grouped: defaultdict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw_value in rows:
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
        start = _position(raw, "start")
        end = _position(raw, "end")
        normalized_message = " ".join(message.split())
        grouped[(relative_path, rule, normalized_message)].append(
            {
                "path": relative_path,
                "rule": rule,
                "message": normalized_message,
                "severity": str(raw.get("severity") or "unknown"),
                "start": start,
                "end": end,
            }
        )

    normalized: list[dict[str, Any]] = []
    for group, group_rows in sorted(grouped.items()):
        ordered = sorted(group_rows, key=_diagnostic_sort_key)
        for ordinal, row in enumerate(ordered):
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
    summary = cast(dict[str, object], summary_value) if isinstance(summary_value, dict) else None
    if not isinstance(summary, dict):
        raise ValueError("BasedPyright output is missing summary")
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
    if baseline.get("coverage", {}).get("state") != "complete":
        blockers.append("baseline coverage is not complete")
    if current.get("coverage", {}).get("state") != "complete":
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
    baseline_keys = set(baseline_rows) - {row["fingerprint"] for row in ambiguous}
    current_keys = set(current_rows) - {row["fingerprint"] for row in ambiguous}
    return {
        "schema": STRICT_DELTA_SCHEMA,
        "new": [current_rows[key] for key in sorted(current_keys - baseline_keys)],
        "persisted": [current_rows[key] for key in sorted(current_keys & baseline_keys)],
        "resolved": [baseline_rows[key] for key in sorted(baseline_keys - current_keys)],
        "unknown": ambiguous,
        "blockers": sorted(set(blockers)),
    }


def _coverage(summary: dict[str, Any], diagnostic_count: int) -> dict[str, Any]:
    files = summary.get("filesAnalyzed")
    errors = summary.get("errorCount")
    warnings = summary.get("warningCount")
    information = summary.get("informationCount")
    expected = sum(value for value in (errors, warnings, information) if isinstance(value, int))
    complete = isinstance(files, int) and files > 0 and expected == diagnostic_count
    return {
        "state": "complete" if complete else "unknown",
        "files_analyzed": files,
        "diagnostics_reported": diagnostic_count,
    }


def _position(raw: dict[str, Any], name: str) -> dict[str, int]:
    value = raw.get("range", {})
    range_map = cast(dict[str, object], value) if isinstance(value, dict) else {}
    position = range_map.get(name)
    if not isinstance(position, dict):
        raise ValueError(f"BasedPyright diagnostic is missing range.{name}")
    position_map = cast(dict[str, object], position)
    line = position_map.get("line")
    character = position_map.get("character")
    if not isinstance(line, int) or not isinstance(character, int):
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
    items = cast(list[object], value)
    rows: dict[str, dict[str, Any]] = {}
    for raw_item in items:
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, Any], raw_item)
        if not isinstance(item.get("fingerprint"), str):
            continue
        rows[item["fingerprint"]] = item
    return rows


def _group(row: dict[str, Any]) -> str:
    return str(row.get("group") or "")
