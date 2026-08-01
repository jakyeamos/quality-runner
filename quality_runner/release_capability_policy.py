from __future__ import annotations

from typing import Any


def required_capabilities(
    *,
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
    script_capabilities: dict[str, tuple[str, ...]],
    file_capabilities: set[str],
) -> set[str] | None:
    if standards_packet.get("profile") != "release":
        return None
    required = {*script_capabilities, "pre_cr"}
    config = standards_packet.get("config")
    if not isinstance(config, dict):
        return required
    configured = config.get("required_capabilities")
    if isinstance(configured, list):
        required.update(
            capability
            for capability in configured
            if isinstance(capability, str)
            and (capability in script_capabilities or capability in file_capabilities)
        )
    gates = config.get("gates")
    if isinstance(gates, list):
        required.update(
            capability_id
            for gate in gates
            if isinstance(gate, dict)
            and gate.get("required") is True
            and isinstance((capability_id := gate.get("id")), str)
            and (capability_id in script_capabilities or capability_id in file_capabilities)
        )
    return required


def required_by(
    *, script_capabilities: dict[str, tuple[str, ...]], profile: object
) -> dict[str, str] | None:
    if profile != "release":
        return None
    return {capability_id: "profile" for capability_id in script_capabilities} | {
        "pre_cr": "profile"
    }
