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
    "pre_pr": ("pre-pr", "prepr", "pre-cr"),
}


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
        capability_id="pre_cr",
        path=scan.get("pre_cr_config"),
        reason="no Pre-CR configuration found",
    )
    _record_file_capability(
        available=available,
        missing=missing,
        capability_id="truth_file",
        path=scan.get("truth_file"),
        reason="no project truth file found",
    )

    profile = standards_packet.get("profile")
    return {
        "schema": CAPABILITY_MAP_SCHEMA,
        "profile": profile if isinstance(profile, str) else None,
        "available": available,
        "missing": missing,
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
    capability_id: str,
    path: object,
    reason: str,
) -> None:
    if isinstance(path, str) and path:
        available.append({"id": capability_id, "type": "file", "source": path})
    else:
        missing.append({"id": capability_id, "type": "file", "reason": reason})
