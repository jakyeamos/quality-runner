from __future__ import annotations

from typing import Any, cast

DATA_CACHE_HINTS = ("cache", "data", "dataset", "external", "corpus", "generated")


def timeout_diagnostics_payload(scan_progress: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scan_progress": scan_progress,
        "pruning_recommendations": scan_pruning_recommendations(scan_progress),
    }
    activity = _scan_activity(scan_progress)
    if activity:
        payload["scan_activity"] = activity
    return payload


def concise_timeout_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    diagnostics = _dict(payload.get("diagnostics")) or {}
    scan_progress = _dict(diagnostics.get("scan_progress")) or {}
    result: dict[str, Any] = {
        **_optional_string("timeout_scope", payload.get("timeout_scope")),
        **_optional_string("reason", payload.get("reason")),
        **_optional_int("timeout_seconds", payload.get("timeout_seconds")),
        **_optional_float("elapsed_seconds", payload.get("elapsed_seconds")),
        **_optional_string("last_directory", scan_progress.get("last_directory")),
        **_optional_int("visited_paths", scan_progress.get("visited_paths")),
        **_optional_int("skipped_paths", scan_progress.get("skipped_paths")),
        "visited_top_level_counts": _string_int_dict(scan_progress.get("visited_top_level_counts")),
        "skipped_top_level_counts": _string_int_dict(scan_progress.get("skipped_top_level_counts")),
        "last_skipped_paths": _string_list(scan_progress.get("last_skipped_paths")),
        "pruning_recommendations": _recommendations(diagnostics.get("pruning_recommendations")),
    }
    activity = _scan_activity(scan_progress)
    if not activity:
        activity = _scan_activity(payload)
    if activity:
        result["scan_activity"] = activity
    return result


def timeout_recommended_action(*, timeout_seconds: int, diagnostics: dict[str, Any]) -> str:
    recommendations = _recommendations(diagnostics.get("pruning_recommendations"))
    first = recommendations[0] if recommendations else None
    pattern = first.get("pattern") if isinstance(first, dict) else None
    if isinstance(pattern, str) and pattern:
        return (
            f"Add `{pattern}` to scan_exclusions only if it is generated/cache data rather "
            f"than source-owned code, rerun refresh, and keep the {timeout_seconds}s total "
            "timeout only if the pruned run still needs more evidence"
        )
    return "Inspect workflow-timeout.json and rerun refresh with tighter scan exclusions or a larger total timeout"


def timeout_diagnostics_markdown(value: object) -> list[str]:
    mapping = _dict(value)
    if mapping is None:
        return []
    lines: list[str] = []
    activity = _scan_activity(mapping)
    if activity:
        kind = activity.get("kind")
        path = activity.get("path")
        if isinstance(kind, str) and isinstance(path, str):
            label = {
                "excluded-directory-estimation": (
                    "excluded-directory estimation (not actual scan work)"
                ),
                "text-scan": "actual text scan",
                "path-traversal": "actual repository traversal",
            }.get(kind, kind)
            lines.append(f"  - Scan activity: {label} at `{path}`")
    last_directory = mapping.get("last_directory")
    if isinstance(last_directory, str) and last_directory:
        lines.append(f"  - Last traversal directory: `{last_directory}`")
    visited_paths = mapping.get("visited_paths")
    skipped_paths = mapping.get("skipped_paths")
    if isinstance(visited_paths, int) or isinstance(skipped_paths, int):
        visited = visited_paths if isinstance(visited_paths, int) else 0
        skipped = skipped_paths if isinstance(skipped_paths, int) else 0
        lines.append(f"  - Scan progress: {visited} visited paths, {skipped} skipped paths")
    recommendations = _recommendations(mapping.get("pruning_recommendations"))
    for recommendation in recommendations:
        pattern = recommendation.get("pattern")
        reason = recommendation.get("reason")
        if isinstance(pattern, str) and pattern:
            line = f"  - Suggested scan exclusion: `{pattern}`"
            if isinstance(reason, str) and reason:
                line += f" ({reason})"
            lines.append(line)
    return lines


def _scan_activity(value: object) -> dict[str, str]:
    mapping = _dict(value)
    if mapping is None:
        return {}
    nested = _dict(mapping.get("scan_activity"))
    if nested is not None:
        nested_activity = _scan_activity(nested)
        if nested_activity:
            return nested_activity
    kind = mapping.get("last_activity_kind")
    path = mapping.get("last_activity_path")
    if not isinstance(kind, str) or not kind:
        kind = mapping.get("kind")
    if not isinstance(path, str) or not path:
        path = mapping.get("path")
    activity: dict[str, str] = {}
    if isinstance(kind, str) and kind:
        activity["kind"] = kind
    if isinstance(path, str) and path:
        activity["path"] = path
    return activity


def scan_pruning_recommendations(scan_progress: dict[str, Any]) -> list[dict[str, Any]]:
    last_directory = scan_progress.get("last_directory")
    if not isinstance(last_directory, str) or not last_directory:
        return []
    if not _looks_like_data_cache_path(last_directory):
        return []
    top_level = last_directory.split("/", 1)[0]
    visited_counts = _string_int_dict(scan_progress.get("visited_top_level_counts"))
    visited_paths = _int_or_zero(scan_progress.get("visited_paths"))
    return [
        {
            "kind": "scan-exclusion",
            "path": last_directory,
            "pattern": f"{last_directory.rstrip('/')}/**",
            "top_level": top_level,
            "top_level_visited_paths": visited_counts.get(top_level, 0),
            "reason": f"timeout ended inside a data/cache-like path after {visited_paths} visited paths",
        }
    ]


def _looks_like_data_cache_path(path: str) -> bool:
    parts = [part.lower() for part in path.split("/") if part]
    return any(any(hint in part for hint in DATA_CACHE_HINTS) for part in parts)


def _recommendations(value: object) -> list[dict[str, Any]]:
    return _dict_list(value)


def _string_int_dict(value: object) -> dict[str, int]:
    mapping = _dict(value)
    if mapping is None:
        return {}
    return {key: item for key, item in mapping.items() if isinstance(item, int)}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[Any], value) if isinstance(item, str) and item]


def _optional_string(key: str, value: object) -> dict[str, str]:
    return {key: value} if isinstance(value, str) and value else {}


def _optional_int(key: str, value: object) -> dict[str, int]:
    return {key: value} if isinstance(value, int) else {}


def _optional_float(key: str, value: object) -> dict[str, float]:
    return {key: value} if isinstance(value, float) else {}


def _int_or_zero(value: object) -> int:
    return value if isinstance(value, int) else 0


def _dict(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in cast(list[Any], value) if isinstance(item, dict)]
