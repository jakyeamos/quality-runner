from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from quality_runner.fleet.audit import (
        fleet_audit_payload,
        fleet_show_payload,
        local_environment_audit_payload,
    )
    from quality_runner.fleet.feed import fleet_feed_payload

__all__ = [
    "fleet_audit_payload",
    "fleet_feed_payload",
    "fleet_show_payload",
    "local_environment_audit_payload",
]


def __getattr__(name: str) -> Any:
    """Load the public fleet entrypoints without importing the audit graph eagerly."""
    if name == "fleet_feed_payload":
        from quality_runner.fleet.feed import fleet_feed_payload

        return fleet_feed_payload
    if name in {
        "fleet_audit_payload",
        "fleet_show_payload",
        "local_environment_audit_payload",
    }:
        from quality_runner.fleet import audit

        return getattr(audit, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
