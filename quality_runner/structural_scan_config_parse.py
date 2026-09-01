from __future__ import annotations

from typing import Any, cast


def parse_structural_scan_section(
    value: object,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(
            _warning(
                "invalid_quality_runner_config_field",
                "quality_runner.structural_scan must be a table",
            )
        )
        return {}

    config = cast(dict[str, Any], value)
    disabled = _string_list(
        config.get("disabled_rule_groups"),
        "quality_runner.structural_scan.disabled_rule_groups",
        warnings,
    )
    include_ignored_paths = _string_list(
        config.get("include_ignored_paths"),
        "quality_runner.structural_scan.include_ignored_paths",
        warnings,
    )
    large_file_lines = _positive_int(
        config.get("large_file_lines"),
        "quality_runner.structural_scan.large_file_lines",
        warnings,
    )
    fat_router_lines = _positive_int(
        config.get("fat_router_lines"),
        "quality_runner.structural_scan.fat_router_lines",
        warnings,
    )
    max_text_files = _positive_int(
        config.get("max_text_files"),
        "quality_runner.structural_scan.max_text_files",
        warnings,
    )
    complexity_thresholds = _positive_int_mapping(
        config.get("complexity_thresholds"),
        "quality_runner.structural_scan.complexity_thresholds",
        warnings,
    )
    report_unverified_complexity_reductions = _bool_value(
        config.get("report_unverified_complexity_reductions"),
        "quality_runner.structural_scan.report_unverified_complexity_reductions",
        warnings,
    )
    similarity_enabled = _bool_value(
        config.get("similarity_enabled"),
        "quality_runner.structural_scan.similarity_enabled",
        warnings,
    )
    similarity_threshold = _unit_interval(
        config.get("similarity_threshold"),
        "quality_runner.structural_scan.similarity_threshold",
        warnings,
    )
    similarity_min_lines = _positive_int(
        config.get("similarity_min_lines"),
        "quality_runner.structural_scan.similarity_min_lines",
        warnings,
    )
    similarity_max_pairs = _positive_int(
        config.get("similarity_max_pairs"),
        "quality_runner.structural_scan.similarity_max_pairs",
        warnings,
    )
    similarity_timeout_seconds = _positive_int(
        config.get("similarity_timeout_seconds"),
        "quality_runner.structural_scan.similarity_timeout_seconds",
        warnings,
    )
    similarity_include_tests = _bool_value(
        config.get("similarity_include_tests"),
        "quality_runner.structural_scan.similarity_include_tests",
        warnings,
    )
    result: dict[str, Any] = {"disabled_rule_groups": disabled}
    if include_ignored_paths:
        result["include_ignored_paths"] = include_ignored_paths
    if large_file_lines is not None:
        result["large_file_lines"] = large_file_lines
    if fat_router_lines is not None:
        result["fat_router_lines"] = fat_router_lines
    if max_text_files is not None:
        result["max_text_files"] = max_text_files
    if complexity_thresholds is not None:
        result["complexity_thresholds"] = complexity_thresholds
    if report_unverified_complexity_reductions is not None:
        result["report_unverified_complexity_reductions"] = report_unverified_complexity_reductions
    if similarity_enabled is not None:
        result["similarity_enabled"] = similarity_enabled
    if similarity_threshold is not None:
        result["similarity_threshold"] = similarity_threshold
    if similarity_min_lines is not None:
        result["similarity_min_lines"] = similarity_min_lines
    if similarity_max_pairs is not None:
        result["similarity_max_pairs"] = similarity_max_pairs
    if similarity_timeout_seconds is not None:
        result["similarity_timeout_seconds"] = similarity_timeout_seconds
    if similarity_include_tests is not None:
        result["similarity_include_tests"] = similarity_include_tests
    return result


def _string_list(value: object, field: str, warnings: list[dict[str, str]]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(
        isinstance(item, str) and item for item in cast(list[object], value)
    ):
        return [item for item in cast(list[object], value) if isinstance(item, str)]
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field", f"{field} must be a list of non-empty strings"
        )
    )
    return []


def _positive_int(value: object, field: str, warnings: list[dict[str, str]]) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and value > 0:
        return value
    warnings.append(
        _warning("invalid_quality_runner_config_field", f"{field} must be a positive integer")
    )
    return None


def _positive_int_mapping(
    value: object,
    field: str,
    warnings: list[dict[str, str]],
) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        warnings.append(_warning("invalid_quality_runner_config_field", f"{field} must be a table"))
        return None
    result: dict[str, int] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str) or key not in {"python", "javascript"}:
            warnings.append(
                _warning(
                    "invalid_quality_runner_config_field",
                    f"{field} supports only python and javascript keys",
                )
            )
            continue
        parsed = _positive_int(item, f"{field}.{key}", warnings)
        if parsed is not None:
            result[key] = parsed
    return result


def _bool_value(value: object, field: str, warnings: list[dict[str, str]]) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    warnings.append(_warning("invalid_quality_runner_config_field", f"{field} must be a boolean"))
    return None


def _unit_interval(value: object, field: str, warnings: list[dict[str, str]]) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and 0 <= float(value) <= 1:
        return float(value)
    warnings.append(
        _warning("invalid_quality_runner_config_field", f"{field} must be a number between 0 and 1")
    )
    return None


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "path": ".quality-runner.toml"}
