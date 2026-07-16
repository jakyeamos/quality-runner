from __future__ import annotations

from datetime import date
from typing import Any


def active_exception(standards_packet: dict[str, Any], capability_id: str) -> dict[str, str] | None:
    config = standards_packet.get("config")
    if not isinstance(config, dict):
        return None
    accepted_exceptions = config.get("accepted_exceptions")
    if not isinstance(accepted_exceptions, list):
        return None

    today = date.today()
    for item in accepted_exceptions:
        if not isinstance(item, dict):
            continue
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
            return {"capability": capability, "reason": reason, "owner": owner, "expires": expires}
    return None
