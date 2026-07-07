from __future__ import annotations

from typing import Any

from quality_runner.capability_state import matching_ci_status
from quality_runner.security.capability_catalog import (
    AGENT_REVIEW_CAPABILITY_IDS,
    RECOMMENDED_COMMANDS,
    SECURITY_COMMAND_CAPABILITIES,
    SECURITY_SCRIPT_ALIASES,
)
from quality_runner.security.config import security_settings


def detect_security_capabilities(
    *,
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
    config: dict[str, Any],
    surfaces: dict[str, bool] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    settings = security_settings(config)
    if not settings["enabled"]:
        return [], []

    required = _required_security_capabilities(settings, standards_packet)
    explicit_required = set(settings["required_capabilities"])
    required_by = "security-baseline" if settings["require_security_baseline"] else "config"
    scripts = _scripts(scan)
    quality_commands = _quality_commands(scan)
    language = _primary_language(scan)
    available: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    discovered_ids: set[str] = set()

    for capability_id in SECURITY_COMMAND_CAPABILITIES:
        command = _first_quality_command(quality_commands, capability_id)
        if command is not None:
            discovered_ids.add(capability_id)
            ci_status = _matching_security_ci_status(scan, capability_id)
            available.append(
                _available_security_command(
                    capability_id=capability_id,
                    command=command,
                    language=language,
                    required_by=required_by if capability_id in required else None,
                    ci_status=ci_status,
                )
            )
            continue

        script_match = _matching_script(scripts, capability_id)
        if script_match is not None:
            discovered_ids.add(capability_id)
            script_name, script_command = script_match
            ci_status = _matching_security_ci_status(scan, capability_id)
            available.append(
                {
                    "id": capability_id,
                    "type": "script",
                    "capability_kind": "local_command",
                    "status": "available",
                    "source": f"package.json:scripts.{script_name}",
                    "command": script_command,
                    "language": language,
                    **({"required_by": required_by} if capability_id in required else {}),
                    **({"ci_status": ci_status} if ci_status else {}),
                    "verification_state": {
                        "discovery": "available",
                        "execution": "not-run",
                        "result": "unknown",
                    },
                }
            )
            continue

        configured = _configured_gate_command(standards_packet, capability_id)
        if configured is not None:
            discovered_ids.add(capability_id)
            available.append(
                {
                    "id": capability_id,
                    "type": "command",
                    "capability_kind": "local_command",
                    "status": "available",
                    "source": configured["source"],
                    "command": configured["command"],
                    "language": configured.get("language", language),
                    **({"required_by": required_by} if capability_id in required else {}),
                    "verification_state": {
                        "discovery": "available",
                        "execution": "not-run",
                        "result": "unknown",
                    },
                }
            )

    if settings["require_security_baseline"]:
        _record_evidence_gaps(
            scan=scan,
            surfaces=surfaces or {},
            discovered_ids=discovered_ids,
            missing=missing,
            language=language,
            required_by=required_by,
        )

    for capability_id in required:
        if capability_id in discovered_ids or capability_id in AGENT_REVIEW_CAPABILITY_IDS:
            continue
        if capability_id in SECURITY_COMMAND_CAPABILITIES and not _has_missing(
            missing, capability_id
        ):
            missing.append(
                _missing_security_command(
                    capability_id=capability_id,
                    language=language,
                    required_by="config" if capability_id in explicit_required else required_by,
                )
            )

    return available, missing


def _has_missing(missing: list[dict[str, Any]], capability_id: str) -> bool:
    return any(item.get("id") == capability_id for item in missing)


def merge_security_capabilities(
    capability_map: dict[str, Any],
    *,
    available: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    agent_review_gates: list[dict[str, Any]],
) -> dict[str, Any]:
    merged_available = [
        *capability_map.get("available", []),
        *available,
        *agent_review_gates,
    ]
    merged_missing = [*capability_map.get("missing", []), *missing]
    return {
        **capability_map,
        "available": merged_available,
        "missing": merged_missing,
        "security_summary": {
            "available_security_capabilities": len(available),
            "missing_security_capabilities": len(missing),
            "agent_review_gates": len(agent_review_gates),
        },
    }


def _record_evidence_gaps(
    *,
    scan: dict[str, Any],
    surfaces: dict[str, bool],
    discovered_ids: set[str],
    missing: list[dict[str, Any]],
    language: str,
    required_by: str,
) -> None:
    has_manifest = _has_dependency_manifest(scan)
    if (
        has_manifest
        and "security_dependency_audit" not in discovered_ids
        and not _has_missing(missing, "security_dependency_audit")
    ):
        missing.append(
            _missing_evidence_capability(
                capability_id="security_dependency_audit",
                reason="dependency manifest present but no vulnerability audit gate detected",
                language=language,
                required_by=required_by,
            )
        )

    if (
        _has_client_framework(scan)
        and "security_secrets_scan" not in discovered_ids
        and not _has_missing(missing, "security_secrets_scan")
    ):
        missing.append(
            _missing_evidence_capability(
                capability_id="security_secrets_scan",
                reason="client framework present but no secrets scan gate detected",
                language=language,
                required_by=required_by,
            )
        )


def _missing_evidence_capability(
    *,
    capability_id: str,
    reason: str,
    language: str,
    required_by: str,
) -> dict[str, Any]:
    return {
        "id": capability_id,
        "type": "evidence",
        "capability_kind": "evidence",
        "status": "missing",
        "reason": reason,
        "language": language,
        "required_by": required_by,
        "recommended_commands": RECOMMENDED_COMMANDS.get(capability_id, []),
        "verification_state": {
            "discovery": "missing",
            "execution": "not-applicable",
            "result": "unknown",
        },
    }


def _missing_security_command(
    *,
    capability_id: str,
    language: str,
    required_by: str,
) -> dict[str, Any]:
    return {
        "id": capability_id,
        "type": "command",
        "capability_kind": "evidence",
        "status": "missing",
        "reason": f"no quality command found for {capability_id}",
        "language": language,
        "required_by": required_by,
        "recommended_commands": RECOMMENDED_COMMANDS.get(capability_id, []),
        "verification_state": {
            "discovery": "missing",
            "execution": "not-applicable",
            "result": "unknown",
        },
    }


def _available_security_command(
    *,
    capability_id: str,
    command: dict[str, str],
    language: str,
    required_by: str | None,
    ci_status: dict[str, str | None] | None,
) -> dict[str, Any]:
    execution = "not-run"
    result = "unknown"
    if ci_status is not None:
        execution = "ci-executed"
        conclusion = ci_status.get("conclusion")
        if conclusion == "success":
            result = "passed"
        elif isinstance(conclusion, str) and conclusion:
            result = "failed"
    return {
        "id": capability_id,
        "type": "command",
        "capability_kind": "ci_only"
        if command.get("local_execution") == "ci-only"
        else "local_command",
        "status": "available",
        "source": command["source"],
        "command": command["command"],
        "language": command.get("language", language),
        **({"required_by": required_by} if required_by else {}),
        **({"ci_status": ci_status} if ci_status else {}),
        "verification_state": {
            "discovery": "available",
            "execution": execution,
            "result": result,
        },
    }


def _matching_security_ci_status(
    scan: dict[str, Any], capability_id: str
) -> dict[str, str | None] | None:
    terms = SECURITY_COMMAND_CAPABILITIES.get(capability_id, ())
    checks = scan.get("ci_checks")
    if not isinstance(checks, list):
        return matching_ci_status(scan, capability_id)
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = check.get("name")
        if not isinstance(name, str):
            continue
        normalized = name.lower()
        if any(term in normalized for term in terms):
            return {
                "name": name,
                "status": _optional_string(check.get("status")),
                "conclusion": _optional_string(check.get("conclusion")),
                "url": _optional_string(check.get("url")),
            }
    return matching_ci_status(scan, capability_id)


def _matching_script(
    scripts: dict[str, str],
    capability_id: str,
) -> tuple[str, str] | None:
    aliases = SECURITY_SCRIPT_ALIASES.get(capability_id, ())
    for script_name, command in scripts.items():
        normalized_name = script_name.lower().replace("_", "-")
        command_lower = command.lower()
        for alias in aliases:
            alias_normalized = alias.lower().replace("_", "-")
            if (
                alias_normalized in normalized_name or alias_normalized in command_lower
            ) and _command_matches_capability(capability_id, command_lower):
                return script_name, command
    return None


def _command_matches_capability(capability_id: str, command_lower: str) -> bool:
    terms = SECURITY_COMMAND_CAPABILITIES.get(capability_id, ())
    return any(term in command_lower for term in terms)


def _configured_gate_command(
    standards_packet: dict[str, Any],
    capability_id: str,
) -> dict[str, str] | None:
    config = standards_packet.get("config")
    if not isinstance(config, dict):
        return None
    gates = config.get("gates")
    if not isinstance(gates, list):
        return None
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict):
            continue
        gate_id = gate.get("id")
        command = gate.get("command")
        ecosystem = gate.get("ecosystem")
        if gate_id == capability_id and isinstance(command, str) and isinstance(ecosystem, str):
            return {
                "command": command,
                "source": f".quality-runner.toml:quality_runner.gates[{index}]",
                "language": ecosystem,
            }
    return None


def _required_security_capabilities(
    settings: dict[str, Any],
    standards_packet: dict[str, Any],
) -> set[str]:
    required = set(settings["required_capabilities"])
    config = standards_packet.get("config")
    if isinstance(config, dict):
        security = config.get("security")
        if isinstance(security, dict):
            explicit = security.get("required_capabilities")
            if isinstance(explicit, list):
                required.update(item for item in explicit if isinstance(item, str))
    return required


def _has_dependency_manifest(scan: dict[str, Any]) -> bool:
    languages = scan.get("languages")
    if isinstance(languages, list):
        return "javascript" in languages or "python" in languages
    ecosystems = scan.get("ecosystems")
    if isinstance(ecosystems, list):
        return bool(ecosystems)
    return False


def _has_client_framework(scan: dict[str, Any]) -> bool:
    scripts = scan.get("scripts")
    if not isinstance(scripts, dict):
        return False
    for command in scripts.values():
        if isinstance(command, str) and any(
            marker in command.lower() for marker in ("next", "nuxt", "vite", "react", "svelte")
        ):
            return True
    package_json_text = str(scan.get("package_manager") or "")
    return package_json_text in {"pnpm", "npm", "yarn"}


def _scripts(scan: dict[str, Any]) -> dict[str, str]:
    scripts = scan.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {
        name: command
        for name, command in scripts.items()
        if isinstance(name, str) and isinstance(command, str) and command
    }


def _quality_commands(scan: dict[str, Any]) -> list[dict[str, str]]:
    commands = scan.get("quality_commands")
    if not isinstance(commands, list):
        return []
    normalized: list[dict[str, str]] = []
    for command in commands:
        if not isinstance(command, dict):
            continue
        capability_id = command.get("id")
        command_text = command.get("command")
        source = command.get("source")
        if (
            isinstance(capability_id, str)
            and capability_id.startswith("security_")
            and isinstance(command_text, str)
            and isinstance(source, str)
        ):
            normalized.append(
                {
                    "id": capability_id,
                    "command": command_text,
                    "source": source,
                    "language": str(command.get("language") or "unknown"),
                    **(
                        {"local_execution": command["local_execution"]}
                        if isinstance(command.get("local_execution"), str)
                        else {}
                    ),
                }
            )
    for command in commands:
        if not isinstance(command, dict):
            continue
        capability_id = command.get("id")
        command_text = command.get("command")
        source = command.get("source")
        language = command.get("language")
        if not (
            isinstance(capability_id, str)
            and capability_id in SECURITY_COMMAND_CAPABILITIES
            and isinstance(command_text, str)
            and isinstance(source, str)
            and isinstance(language, str)
        ):
            continue
        if any(existing["id"] == capability_id for existing in normalized):
            continue
        normalized.append(
            {
                "id": capability_id,
                "command": command_text,
                "source": source,
                "language": language,
                **(
                    {"local_execution": command["local_execution"]}
                    if isinstance(command.get("local_execution"), str)
                    else {}
                ),
            }
        )
    return normalized


def _first_quality_command(
    commands: list[dict[str, str]],
    capability_id: str,
) -> dict[str, str] | None:
    for command in commands:
        if command["id"] == capability_id:
            return command
    return None


def _primary_language(scan: dict[str, Any]) -> str:
    languages = scan.get("languages")
    if isinstance(languages, list):
        for language in languages:
            if isinstance(language, str) and language:
                return language
    return "unknown"


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
