from __future__ import annotations

from quality_runner.scan_exclusions import SCAN_EXCLUSION_MODULES, normalize_scan_exclusion_module


def parse_scan_exclusions_by_module(
    value: object,
) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    if value is None:
        return {}, []
    if not isinstance(value, dict):
        return {}, [_warning("quality_runner.scan_exclusions_by_module must be a table")]
    parsed: dict[str, list[str]] = {}
    warnings: list[dict[str, str]] = []
    for raw_module, raw_patterns in value.items():
        if not isinstance(raw_module, str) or not raw_module:
            warnings.append(
                _warning("quality_runner.scan_exclusions_by_module keys must be module names")
            )
            continue
        try:
            module = normalize_scan_exclusion_module(raw_module)
        except ValueError:
            allowed = ", ".join(SCAN_EXCLUSION_MODULES)
            warnings.append(
                _warning(
                    f"quality_runner.scan_exclusions_by_module.{raw_module} is unsupported; "
                    f"expected one of: {allowed}"
                )
            )
            continue
        if module in parsed:
            warnings.append(
                _warning(f"quality_runner.scan_exclusions_by_module.{module} is duplicated")
            )
            continue
        parsed[module] = _string_list(
            raw_patterns,
            f"quality_runner.scan_exclusions_by_module.{raw_module}",
            warnings,
        )
    return parsed, warnings


def _string_list(
    value: object,
    field: str,
    warnings: list[dict[str, str]],
) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    warnings.append(_warning(f"{field} must be a list of non-empty strings"))
    return []


def _warning(message: str) -> dict[str, str]:
    return {"code": "invalid_quality_runner_config_field", "message": message}
