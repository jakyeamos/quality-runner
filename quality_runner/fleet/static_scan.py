from __future__ import annotations

from typing import Any, cast


def static_scan_repository(repository: dict[str, Any]) -> dict[str, Any]:
    """Use the clean canonical target checkout for static evidence when ready."""

    target_value = repository.get("target_branch")
    if not isinstance(target_value, dict):
        return repository
    target = cast(dict[str, Any], target_value)
    if target.get("status") != "ready":
        return repository
    checkout_id = target.get("checkout_id")
    if not isinstance(checkout_id, str):
        return repository
    for raw in cast(list[object], repository.get("checkouts", [])):
        if not isinstance(raw, dict):
            continue
        checkout = cast(dict[str, Any], raw)
        if checkout.get("checkout_id") != checkout_id:
            continue
        path = checkout.get("path")
        if isinstance(path, str) and path:
            return {**repository, "primary_path": path}
    return repository
