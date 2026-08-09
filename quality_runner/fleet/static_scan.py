from __future__ import annotations

from typing import Any


def static_scan_repository(repository: dict[str, Any]) -> dict[str, Any]:
    """Use the clean canonical target checkout for static evidence when ready."""

    target = repository.get("target_branch")
    if not isinstance(target, dict) or target.get("status") != "ready":
        return repository
    checkout_id = target.get("checkout_id")
    if not isinstance(checkout_id, str):
        return repository
    for checkout in repository.get("checkouts", []):
        if not isinstance(checkout, dict) or checkout.get("checkout_id") != checkout_id:
            continue
        path = checkout.get("path")
        if isinstance(path, str) and path:
            return {**repository, "primary_path": path}
    return repository
