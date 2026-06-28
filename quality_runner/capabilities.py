from __future__ import annotations

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


def detect_capabilities(
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
) -> dict[str, Any]:
    scripts = _scripts(scan)
    available: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    for capability_id, script_names in SCRIPT_CAPABILITIES.items():
        script_name = _first_matching_script(scripts, script_names)
        if script_name is None:
            missing.append(
                {
                    "id": capability_id,
                    "type": "script",
                    "reason": f"no package script found for {capability_id}",
                }
            )
        else:
            available.append(
                {
                    "id": capability_id,
                    "type": "script",
                    "source": f"package.json:scripts.{script_name}",
                }
            )

    _record_file_capability(
        available=available,
        missing=missing,
        scripts=scripts,
        capability_id="pre_cr",
        script_names=PRE_CR_SCRIPT_NAMES,
        path=scan.get("pre_cr_config"),
        reason="no Pre-CR script or configuration found",
    )
    _record_file_capability(
        available=available,
        missing=missing,
        scripts=scripts,
        capability_id="truth_file",
        script_names=(),
        path=scan.get("truth_file"),
        reason="no project truth file found",
    )

    profile = standards_packet.get("profile")
    return {
        "schema": CAPABILITY_MAP_SCHEMA,
        "profile": profile if isinstance(profile, str) else None,
        "available": available,
        "missing": missing,
        "warnings": _warnings(scan),
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


def _record_file_capability(
    *,
    available: list[dict[str, str]],
    missing: list[dict[str, str]],
    scripts: dict[str, str],
    capability_id: str,
    script_names: tuple[str, ...],
    path: object,
    reason: str,
) -> None:
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
        missing.append({"id": capability_id, "type": "file", "reason": reason})


def _has_capability(capabilities: list[dict[str, str]], capability_id: str) -> bool:
    return any(capability.get("id") == capability_id for capability in capabilities)


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
