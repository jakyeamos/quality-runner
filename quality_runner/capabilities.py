from __future__ import annotations

from datetime import date
from typing import Any

CAPABILITY_MAP_SCHEMA = "quality-runner-capability-map-v0.1"

SCRIPT_CAPABILITIES = {
    "formatter": ("format", "fmt", "prettier"),
    "lint": ("lint",),
    "typecheck": ("typecheck", "type-check", "check-types"),
    "tests": ("test", "tests"),
    "build": ("build",),
    "dead_code": ("dead-code", "dead_code", "knip", "vulture", "unused"),
    "runtime_smoke": ("smoke", "runtime-smoke", "smoke-test"),
    "pre_pr": ("pre-pr", "prepr"),
}
PRE_CR_SCRIPT_NAMES = ("pre-cr", "precr", "pre-cr:run")
FILE_CAPABILITIES = {"pre_cr", "truth_file"}


def detect_capabilities(
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
) -> dict[str, Any]:
    scripts = _scripts(scan)
    required_capabilities = _required_capabilities(standards_packet)
    accepted_exceptions: list[dict[str, str]] = []
    available: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    for capability_id, script_names in SCRIPT_CAPABILITIES.items():
        if capability_id not in required_capabilities:
            continue
        script_name = _first_matching_script(scripts, script_names)
        if script_name is None:
            _record_missing(
                missing=missing,
                accepted_exceptions=accepted_exceptions,
                standards_packet=standards_packet,
                capability=dict(
                    id=capability_id,
                    type="script",
                    reason=f"no package script found for {capability_id}",
                ),
            )
        else:
            available.append(
                {
                    "id": capability_id,
                    "type": "script",
                    "source": f"package.json:scripts.{script_name}",
                }
            )

    # fmt: off
    if "pre_cr" in required_capabilities:
        _record_file_capability(available=available, missing=missing, accepted_exceptions=accepted_exceptions, standards_packet=standards_packet, scripts=scripts, capability_id="pre_cr", script_names=PRE_CR_SCRIPT_NAMES, path=scan.get("pre_cr_config"), reason="no Pre-CR script or configuration found")
    if "truth_file" in required_capabilities:
        _record_file_capability(available=available, missing=missing, accepted_exceptions=accepted_exceptions, standards_packet=standards_packet, scripts=scripts, capability_id="truth_file", script_names=(), path=scan.get("truth_file"), reason="no project truth file found")
    # fmt: on

    profile = standards_packet.get("profile")
    return {
        "schema": CAPABILITY_MAP_SCHEMA,
        "profile": profile if isinstance(profile, str) else None,
        "available": available,
        "missing": missing,
        "accepted_exceptions": accepted_exceptions,
        "warnings": _combined_warnings(scan, standards_packet),
    }


def _scripts(scan: dict[str, Any]) -> dict[str, str]:
    scripts = scan.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {
        name: command
        for name, command in scripts.items()
        if isinstance(name, str) and isinstance(command, str) and command
    }


def _first_matching_script(
    scripts: dict[str, str],
    script_names: tuple[str, ...],
) -> str | None:
    for script_name in script_names:
        if script_name in scripts:
            return script_name
    return None


# fmt: off
def _record_file_capability(*, available: list[dict[str, str]], missing: list[dict[str, str]], accepted_exceptions: list[dict[str, str]], standards_packet: dict[str, Any], scripts: dict[str, str], capability_id: str, script_names: tuple[str, ...], path: object, reason: str) -> None:
# fmt: on
    script_name = _first_matching_script(scripts, script_names)
    if script_name is not None:
        available.append(
            {
                "id": capability_id,
                "type": "script",
                "source": f"package.json:scripts.{script_name}",
            }
        )
    elif isinstance(path, str) and path:
        if not _has_capability(available, capability_id):
            available.append({"id": capability_id, "type": "file", "source": path})
    elif not _has_capability(available, capability_id):
        _record_missing(
            missing=missing,
            accepted_exceptions=accepted_exceptions,
            standards_packet=standards_packet,
            capability=dict(id=capability_id, type="file", reason=reason),
        )


def _has_capability(capabilities: list[dict[str, str]], capability_id: str) -> bool:
    return any(capability.get("id") == capability_id for capability in capabilities)


# fmt: off
def _record_missing(*, missing: list[dict[str, str]], accepted_exceptions: list[dict[str, str]], standards_packet: dict[str, Any], capability: dict[str, str]) -> None:
# fmt: on
    exception = _active_exception(standards_packet, capability["id"])
    if exception is None:
        missing.append(capability)
    else:
        accepted_exceptions.append(exception)


def _required_capabilities(standards_packet: dict[str, Any]) -> set[str]:
    config = standards_packet.get("config")
    if isinstance(config, dict):
        if config.get("required_capabilities_configured") is not True:
            return {*SCRIPT_CAPABILITIES, *FILE_CAPABILITIES}
        required_capabilities = config.get("required_capabilities")
        if isinstance(required_capabilities, list):
            return {
                capability
                for capability in required_capabilities
                if isinstance(capability, str)
                and (capability in SCRIPT_CAPABILITIES or capability in FILE_CAPABILITIES)
            }
    return {*SCRIPT_CAPABILITIES, *FILE_CAPABILITIES}


def _active_exception(standards_packet: dict[str, Any], capability_id: str) -> dict[str, str] | None:
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
        expires = item.get("expires")
        if not (
            isinstance(capability, str)
            and capability == capability_id
            and isinstance(reason, str)
            and reason
            and isinstance(expires, str)
            and expires
        ):
            continue
        try:
            expires_on = date.fromisoformat(expires)
        except ValueError:
            continue
        if expires_on >= today:
            return {"capability": capability, "reason": reason, "expires": expires}
    return None


def _warnings(scan: dict[str, Any]) -> list[dict[str, str]]:
    warnings = scan.get("warnings")
    if not isinstance(warnings, list):
        return []

    normalized: list[dict[str, str]] = []
    for warning in warnings:
        if not isinstance(warning, dict):
            continue
        code = warning.get("code")
        message = warning.get("message")
        path = warning.get("path")
        if isinstance(code, str) and isinstance(message, str) and isinstance(path, str):
            normalized.append({"code": code, "message": message, "path": path})
    return normalized


def _combined_warnings(
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
) -> list[dict[str, str]]:
    combined: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for warning in [*_warnings(scan), *_warnings(standards_packet)]:
        key = (warning["code"], warning["message"], warning["path"])
        if key not in seen:
            combined.append(warning)
            seen.add(key)
    return combined
