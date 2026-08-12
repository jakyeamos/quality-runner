from __future__ import annotations

from datetime import date
from typing import Any, cast


def active_exception(standards_packet: dict[str, Any], capability_id: str) -> dict[str, str] | None:
    config = standards_packet.get("config")
    if not isinstance(config, dict):
        return None
    config_data = cast(dict[str, object], config)
    accepted_exceptions = config_data.get("accepted_exceptions")
    if not isinstance(accepted_exceptions, list):
        return None

    today = date.today()
    for raw_item in cast(list[object], accepted_exceptions):
        if not isinstance(raw_item, dict):
            continue
        item = cast(dict[str, object], raw_item)
        capability = item.get("capability")
        reason = item.get("reason")
        owner = item.get("owner")
        expires = item.get("expires")
        if not (
            isinstance(capability, str)
            and capability == capability_id
            and isinstance(reason, str)
            and reason
            and isinstance(owner, str)
            and owner
            and isinstance(expires, str)
            and expires
        ):
            continue
        try:
            expires_on = date.fromisoformat(expires)
        except ValueError:
            continue
        if expires_on >= today:
            return {
                "capability": capability,
                "reason": reason,
                "owner": owner,
                "expires": expires,
                "evidence_state": "not_applicable",
            }
    return None
