from __future__ import annotations

from typing import Any, cast

DEFAULT_BUNDLE_BUDGET_GZIP_BYTES = 200_000
DEFAULT_TOTAL_BUNDLE_BUDGET_GZIP_BYTES = 800_000
VALID_APPLICABILITY = {"public_web", "internal_web", "not_applicable", "unknown"}


def parse_web_readiness_section(
    value: object,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(_warning("quality_runner.web_readiness must be a table"))
        return {}
    value = cast(dict[str, Any], value)

    applicability = value.get("applicability", "unknown")
    if not isinstance(applicability, str) or applicability not in VALID_APPLICABILITY:
        warnings.append(
            _warning(
                "quality_runner.web_readiness.applicability must be public_web, "
                "internal_web, not_applicable, or unknown"
            )
        )
        applicability = "unknown"

    reason = value.get("reason")
    if reason is not None and (not isinstance(reason, str) or not reason.strip()):
        warnings.append(_warning("quality_runner.web_readiness.reason must be a non-empty string"))
        reason = None
    if applicability == "not_applicable" and reason is None:
        warnings.append(
            _warning(
                "quality_runner.web_readiness.reason is required when applicability "
                "is not_applicable"
            )
        )
        applicability = "unknown"

    routes = _string_list(value.get("routes"), "routes", warnings)
    build_roots = _string_list(value.get("build_roots"), "build_roots", warnings)
    bundle_budget = _positive_int(
        value.get("bundle_budget_gzip_bytes"),
        "bundle_budget_gzip_bytes",
        warnings,
        DEFAULT_BUNDLE_BUDGET_GZIP_BYTES,
    )
    total_bundle_budget = _positive_int(
        value.get("total_bundle_budget_gzip_bytes"),
        "total_bundle_budget_gzip_bytes",
        warnings,
        DEFAULT_TOTAL_BUNDLE_BUDGET_GZIP_BYTES,
    )

    return {
        "applicability": applicability,
        "reason": reason.strip() if isinstance(reason, str) else None,
        "routes": routes,
        "build_roots": build_roots,
        "bundle_budget_gzip_bytes": bundle_budget,
        "total_bundle_budget_gzip_bytes": total_bundle_budget,
    }


def _string_list(
    value: object,
    field: str,
    warnings: list[dict[str, str]],
) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        values = cast(list[object], value)
        if all(isinstance(item, str) and item.strip() for item in values):
            return sorted({item.strip() for item in values if isinstance(item, str)})
    warnings.append(
        _warning(f"quality_runner.web_readiness.{field} must be a list of non-empty strings")
    )
    return []


def _positive_int(
    value: object,
    field: str,
    warnings: list[dict[str, str]],
    default: int,
) -> int:
    if value is None:
        return default
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    warnings.append(_warning(f"quality_runner.web_readiness.{field} must be a positive integer"))
    return default


def _warning(message: str) -> dict[str, str]:
    return {
        "code": "invalid_quality_runner_config_field",
        "message": message,
    }
