from __future__ import annotations

from datetime import date
from typing import Any

from quality_runner.schema_constants import CAPABILITY_MAP_SCHEMA

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
    quality_commands = [*_quality_commands(scan), *_configured_quality_commands(standards_packet)]
    required_capabilities = _required_capabilities(scan, standards_packet)
    required_by = _required_by(standards_packet)
    accepted_exceptions: list[dict[str, str]] = []
    available: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for capability_id, script_names in SCRIPT_CAPABILITIES.items():
        if capability_id not in required_capabilities:
            continue
        command = _first_quality_command(quality_commands, capability_id)
        script_name = _first_matching_script(scripts, script_names)
        if command is not None:
            available.append(
                _available_command(
                    capability_id=capability_id,
                    command=command,
                    required_by=required_by.get(capability_id),
                    ci_status=_matching_ci_status(scan, capability_id),
                )
            )
        elif script_name is None:
            _record_missing(
                missing=missing,
                accepted_exceptions=accepted_exceptions,
                standards_packet=standards_packet,
                capability=dict(
                    id=capability_id,
                    type="command",
                    reason=f"no quality command found for {capability_id}",
                    language=_primary_language(scan),
                    required_by=required_by.get(capability_id, "profile"),
                ),
            )
        else:
            available.append(
                {
                    "id": capability_id,
                    "type": "script",
                    "source": f"package.json:scripts.{script_name}",
                    **_optional_field("required_by", required_by.get(capability_id)),
                    **_optional_field("ci_status", _matching_ci_status(scan, capability_id)),
                }
            )

    # fmt: off
    if "pre_cr" in required_capabilities:
        _record_file_capability(available=available, missing=missing, accepted_exceptions=accepted_exceptions, standards_packet=standards_packet, scan=scan, scripts=scripts, quality_commands=quality_commands, capability_id="pre_cr", script_names=PRE_CR_SCRIPT_NAMES, path=scan.get("pre_cr_config"), reason="no Pre-CR script or configuration found", language=_primary_language(scan), required_by=required_by.get("pre_cr", "profile"))
    if "truth_file" in required_capabilities:
        _record_file_capability(available=available, missing=missing, accepted_exceptions=accepted_exceptions, standards_packet=standards_packet, scan=scan, scripts=scripts, quality_commands=quality_commands, capability_id="truth_file", script_names=(), path=scan.get("truth_file"), reason="no project truth file found", language=_primary_language(scan), required_by=required_by.get("truth_file", "profile"))
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
        language = command.get("language")
        owner = command.get("owner")
        severity = command.get("severity")
        if (
            isinstance(capability_id, str)
            and capability_id
            and isinstance(command_text, str)
            and command_text
            and isinstance(source, str)
            and source
            and isinstance(language, str)
            and language
        ):
            normalized.append(
                {
                    "id": capability_id,
                    "command": command_text,
                    "source": source,
                    "language": language,
                    **_optional_field("owner", owner),
                    **_optional_field("severity", severity),
                }
            )
    return normalized


def _configured_quality_commands(standards_packet: dict[str, Any]) -> list[dict[str, str]]:
    config = standards_packet.get("config")
    if not isinstance(config, dict):
        return []
    gates = config.get("gates")
    if not isinstance(gates, list):
        return []

    commands: list[dict[str, str]] = []
    for index, gate in enumerate(gates):
        if not isinstance(gate, dict) or gate.get("required") is not True:
            continue
        capability_id = gate.get("id")
        command = gate.get("command")
        ecosystem = gate.get("ecosystem")
        owner = gate.get("owner")
        severity = gate.get("severity")
        if not (
            isinstance(capability_id, str)
            and capability_id
            and isinstance(command, str)
            and command
            and isinstance(ecosystem, str)
            and ecosystem
            and isinstance(owner, str)
            and owner
            and isinstance(severity, str)
            and severity
        ):
            continue
        commands.append(
            {
                "id": capability_id,
                "command": command,
                "source": f".quality-runner.toml:quality_runner.gates[{index}]",
                "language": ecosystem,
                "owner": owner,
                "severity": severity,
            }
        )
    return commands


def _first_quality_command(
    commands: list[dict[str, str]],
    capability_id: str,
) -> dict[str, str] | None:
    for command in commands:
        if command["id"] == capability_id:
            return command
    return None


def _first_matching_script(
    scripts: dict[str, str],
    script_names: tuple[str, ...],
) -> str | None:
    for script_name in script_names:
        if script_name in scripts:
            return script_name
    return None


# fmt: off
def _record_file_capability(*, available: list[dict[str, Any]], missing: list[dict[str, Any]], accepted_exceptions: list[dict[str, str]], standards_packet: dict[str, Any], scan: dict[str, Any], scripts: dict[str, str], quality_commands: list[dict[str, str]], capability_id: str, script_names: tuple[str, ...], path: object, reason: str, language: str, required_by: str | None) -> None:
# fmt: on
    command = _first_quality_command(quality_commands, capability_id)
    if command is not None:
        available.append(
            _available_command(
                capability_id=capability_id,
                command=command,
                required_by=required_by,
                ci_status=_matching_ci_status(scan, capability_id),
            )
        )
        return

    script_name = _first_matching_script(scripts, script_names)
    if script_name is not None:
        available.append(
            {
                "id": capability_id,
                "type": "script",
                "source": f"package.json:scripts.{script_name}",
                **_optional_field("required_by", required_by),
                **_optional_field("ci_status", _matching_ci_status(scan, capability_id)),
            }
        )
    elif isinstance(path, str) and path:
        if not _has_capability(available, capability_id):
            available.append(
                {
                    "id": capability_id,
                    "type": "file",
                    "source": path,
                    **_optional_field("required_by", required_by),
                }
            )
    elif not _has_capability(available, capability_id):
        _record_missing(
            missing=missing,
            accepted_exceptions=accepted_exceptions,
            standards_packet=standards_packet,
            capability=dict(
                id=capability_id,
                type="file",
                reason=reason,
                language=language,
                **_optional_field("required_by", required_by),
            ),
        )


def _has_capability(capabilities: list[dict[str, Any]], capability_id: str) -> bool:
    return any(capability.get("id") == capability_id for capability in capabilities)


# fmt: off
def _record_missing(*, missing: list[dict[str, Any]], accepted_exceptions: list[dict[str, str]], standards_packet: dict[str, Any], capability: dict[str, Any]) -> None:
# fmt: on
    exception = _active_exception(standards_packet, capability["id"])
    if exception is None:
        missing.append(capability)
    else:
        accepted_exceptions.append(exception)


def _required_capabilities(scan: dict[str, Any], standards_packet: dict[str, Any]) -> set[str]:
    config = standards_packet.get("config")
    if isinstance(config, dict):
        required_capabilities = config.get("required_capabilities")
        if config.get("required_capabilities_configured") is True and isinstance(
            required_capabilities, list
        ):
            return {
                capability
                for capability in required_capabilities
                if isinstance(capability, str)
                and (capability in SCRIPT_CAPABILITIES or capability in FILE_CAPABILITIES)
            }

    required = {*SCRIPT_CAPABILITIES, "pre_cr"}
    if isinstance(config, dict):
        gates = config.get("gates")
        if isinstance(gates, list):
            for gate in gates:
                if isinstance(gate, dict) and gate.get("required") is True:
                    capability_id = gate.get("id")
                    if isinstance(capability_id, str) and (
                        capability_id in SCRIPT_CAPABILITIES or capability_id in FILE_CAPABILITIES
                    ):
                        required.add(capability_id)
    if _truth_file_required(scan):
        required.add("truth_file")
    return required


def _required_by(standards_packet: dict[str, Any]) -> dict[str, str]:
    config = standards_packet.get("config")
    if not isinstance(config, dict):
        return {}
    required_capabilities = config.get("required_capabilities")
    if config.get("required_capabilities_configured") is not True or not isinstance(
        required_capabilities, list
    ):
        return {}
    return {
        capability: "config"
        for capability in required_capabilities
        if isinstance(capability, str)
        and (capability in SCRIPT_CAPABILITIES or capability in FILE_CAPABILITIES)
    }


def _truth_file_required(scan: dict[str, Any]) -> bool:
    if isinstance(scan.get("truth_file"), str) and scan["truth_file"]:
        return True
    instruction_files = scan.get("agent_instruction_files")
    if not isinstance(instruction_files, list):
        return False
    quality_contract = scan.get("quality_contract")
    if not isinstance(quality_contract, dict):
        return False
    required_terms = quality_contract.get("required_terms")
    if not isinstance(required_terms, dict):
        return False
    return required_terms.get("truth_file") is True


def _primary_language(scan: dict[str, Any]) -> str:
    languages = scan.get("languages")
    if isinstance(languages, list):
        for language in languages:
            if isinstance(language, str) and language:
                return language
    return "unknown"


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


def _available_command(
    *,
    capability_id: str,
    command: dict[str, str],
    required_by: str | None,
    ci_status: dict[str, str | None] | None,
) -> dict[str, Any]:
    return {
        "id": capability_id,
        "type": "command",
        "source": command["source"],
        "command": command["command"],
        "language": command["language"],
        **_optional_field("required_by", required_by),
        **_optional_field("owner", command.get("owner")),
        **_optional_field("severity", command.get("severity")),
        **_optional_field("ci_status", ci_status),
    }


def _matching_ci_status(
    scan: dict[str, Any],
    capability_id: str,
) -> dict[str, str | None] | None:
    checks = scan.get("ci_checks")
    if not isinstance(checks, list):
        return None
    terms = {
        "formatter": ("format", "fmt", "prettier"),
        "lint": ("lint",),
        "typecheck": ("typecheck", "type-check", "types"),
        "tests": ("test", "tests"),
        "build": ("build",),
        "dead_code": ("dead", "unused", "knip", "vulture"),
        "runtime_smoke": ("smoke",),
        "pre_pr": ("pull request", "pre-pr", "pre pr"),
        "pre_cr": ("pre-cr", "pre cr"),
    }.get(capability_id, (capability_id,))
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
    return None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_field(key: str, value: object) -> dict[str, Any]:
    if value is None:
        return {}
    return {key: value}


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
