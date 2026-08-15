from __future__ import annotations

from typing import Any, cast

CONFIG_FILE_NAME = ".quality-runner.toml"


def parse_maintenance_surface_section(
    value: object,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(_warning("quality_runner.maintenance_surface must be a table"))
        return {}

    section = cast(dict[str, object], value)
    result: dict[str, Any] = {}
    enabled = section.get("enabled")
    if enabled is not None:
        if isinstance(enabled, bool):
            result["enabled"] = enabled
        else:
            warnings.append(
                _warning("quality_runner.maintenance_surface.enabled must be a boolean")
            )

    result["behavior_owners"] = _contract_list(
        section.get("behavior_owners"),
        field="behavior_owners",
        required_fields=("id", "owner"),
        warnings=warnings,
    )
    result["compatibility"] = _contract_list(
        section.get("compatibility"),
        field="compatibility",
        required_fields=("id", "consumer", "owner", "behavior", "removal_condition"),
        warnings=warnings,
    )
    return result


def _contract_list(
    value: object,
    *,
    field: str,
    required_fields: tuple[str, ...],
    warnings: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if value is None:
        return []
    path = f"quality_runner.maintenance_surface.{field}"
    if not isinstance(value, list):
        warnings.append(_warning(f"{path} must be a list of tables"))
        return []

    items = cast(list[object], value)
    contracts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw_item in enumerate(items):
        item_path = f"{path}[{index}]"
        if not isinstance(raw_item, dict):
            warnings.append(_warning(f"{item_path} must be a table"))
            continue
        item = cast(dict[str, object], raw_item)
        missing = [name for name in required_fields if not _non_empty_string(item.get(name))]
        paths = _string_list(item.get("paths"))
        if not paths:
            missing.append("paths")
        if missing:
            warnings.append(_warning(f"{item_path} requires non-empty {', '.join(missing)}"))
            continue
        contract_id = str(item["id"])
        if contract_id in seen_ids:
            warnings.append(_warning(f"{item_path}.id must be unique: {contract_id}"))
            continue
        seen_ids.add(contract_id)
        contract: dict[str, Any] = {name: str(item[name]) for name in required_fields}
        contract["paths"] = paths
        description = _non_empty_string(item.get("description"))
        if description:
            contract["description"] = description
        contracts.append(contract)
    return contracts


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str) and item]


def _non_empty_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _warning(message: str) -> dict[str, str]:
    return {
        "code": "invalid_quality_runner_config_field",
        "message": message,
        "path": CONFIG_FILE_NAME,
    }
