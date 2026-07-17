from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from quality_runner.architecture_config_parse import parse_architecture_section
from quality_runner.artifact_config_parse import parse_artifacts_section
from quality_runner.integrate_config_parse import parse_integrate_section
from quality_runner.security.config_parse import parse_security_section
from quality_runner.skills_config_parse import parse_skills_section
from quality_runner.structural_scan_config_parse import parse_structural_scan_section

CONFIG_FILE_NAME = ".quality-runner.toml"
CONFIG_SCHEMA = "quality-runner-config-v0.1"
PROFILE_EXTENDS_DEFAULT = "default"
ACCEPTED_DISPOSITION_STATUSES = {
    "accepted-intentional",
    "accepted-false-positive",
    "blocked-with-prerequisite",
}


def load_repo_config(repo_root: Path) -> dict[str, Any]:
    path = repo_root.expanduser().resolve() / CONFIG_FILE_NAME
    if not path.exists():
        return _empty_config(path=None, warnings=[])

    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        return _empty_config(
            path=CONFIG_FILE_NAME,
            warnings=[
                _warning(
                    "invalid_quality_runner_config",
                    f"{CONFIG_FILE_NAME} could not be parsed as TOML: {error}",
                )
            ],
        )

    section = payload.get("quality_runner")
    if not isinstance(section, dict):
        return _empty_config(path=CONFIG_FILE_NAME, warnings=[])

    warnings: list[dict[str, str]] = []
    default_profile = _string_value(
        section.get("default_profile"), "quality_runner.default_profile", warnings
    )
    profiles = _profiles(section.get("profiles"), warnings)
    required = _string_list(
        section.get("required_capabilities"), "quality_runner.required_capabilities", warnings
    )
    allowed_package_managers = _string_list(
        section.get("allowed_package_managers"),
        "quality_runner.allowed_package_managers",
        warnings,
    )
    scan_exclusions = _string_list(
        section.get("scan_exclusions"), "quality_runner.scan_exclusions", warnings
    )
    gates = _gates(section.get("gates"), warnings)
    exceptions = _accepted_exceptions(section.get("accepted_exceptions"), warnings)
    accepted_dispositions = _accepted_dispositions(section.get("accepted_dispositions"), warnings)
    gate_timeouts = _positive_int_mapping(
        section.get("gate_timeouts"), "quality_runner.gate_timeouts", warnings
    )
    severity_overrides = _string_mapping(
        section.get("severity_overrides"), "quality_runner.severity_overrides", warnings
    )
    artifacts = parse_artifacts_section(section.get("artifacts"), warnings)
    structural_scan = parse_structural_scan_section(section.get("structural_scan"), warnings)
    integrate = parse_integrate_section(section.get("integrate"), warnings)
    architecture = parse_architecture_section(section.get("architecture"), warnings)
    security = parse_security_section(section.get("security"), warnings)
    skills = parse_skills_section(section.get("skills"), warnings)
    payload = _config(
        path=CONFIG_FILE_NAME,
        default_profile=default_profile,
        profiles=profiles,
        required_capabilities=required,
        required_capabilities_configured="required_capabilities" in section,
        allowed_package_managers=allowed_package_managers,
        scan_exclusions=scan_exclusions,
        accepted_exceptions=exceptions,
        accepted_dispositions=accepted_dispositions,
        gates=gates,
        gate_timeouts=gate_timeouts,
        severity_overrides=severity_overrides,
        structural_scan=structural_scan,
        warnings=warnings,
    )
    if integrate:
        payload["integrate"] = integrate
    if architecture:
        payload["architecture"] = architecture
    if security:
        payload["security"] = security
    if skills:
        payload["skills"] = skills
    if artifacts:
        payload["artifacts"] = artifacts
    return payload


# fmt: off
def _config(
    *, path: str | None, default_profile: str | None, profiles: dict[str, dict[str, Any]], required_capabilities: list[str], required_capabilities_configured: bool, allowed_package_managers: list[str], scan_exclusions: list[str], accepted_exceptions: list[dict[str, str]], accepted_dispositions: list[dict[str, str]], gates: list[dict[str, Any]], gate_timeouts: dict[str, int], severity_overrides: dict[str, str], structural_scan: dict[str, Any], warnings: list[dict[str, str]],
) -> dict[str, Any]:
    return dict(
        schema=CONFIG_SCHEMA, path=path, default_profile=default_profile, profiles=profiles, required_capabilities=required_capabilities, required_capabilities_configured=required_capabilities_configured, allowed_package_managers=allowed_package_managers, scan_exclusions=scan_exclusions, accepted_exceptions=accepted_exceptions, accepted_dispositions=accepted_dispositions, gates=gates, gate_timeouts=gate_timeouts, severity_overrides=severity_overrides, structural_scan=structural_scan, warnings=warnings,
    )
# fmt: on


def _empty_config(*, path: str | None, warnings: list[dict[str, str]]) -> dict[str, Any]:
    return _config(
        path=path,
        default_profile=None,
        profiles={},
        required_capabilities=[],
        required_capabilities_configured=False,
        allowed_package_managers=[],
        scan_exclusions=[],
        accepted_exceptions=[],
        accepted_dispositions=[],
        gates=[],
        gate_timeouts={},
        severity_overrides={},
        structural_scan={},
        warnings=warnings,
    )


def _string_value(value: object, field: str, warnings: list[dict[str, str]]) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value:
        return value
    warnings.append(
        _warning("invalid_quality_runner_config_field", f"{field} must be a non-empty string")
    )
    return None


def _string_list(value: object, field: str, warnings: list[dict[str, str]]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(item, str) and item for item in value):
        return value
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f"{field} must be a list of non-empty strings",
        )
    )
    return []


def _string_mapping(
    value: object,
    field: str,
    warnings: list[dict[str, str]],
) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, dict) and all(
        isinstance(key, str) and key and isinstance(item, str) and item
        for key, item in value.items()
    ):
        return dict(value)
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f"{field} must be a table of non-empty string values",
        )
    )
    return {}


def _positive_int_mapping(
    value: object,
    field: str,
    warnings: list[dict[str, str]],
) -> dict[str, int]:
    if value is None:
        return {}
    if isinstance(value, dict) and all(
        isinstance(key, str) and key and isinstance(item, int) and item > 0
        for key, item in value.items()
    ):
        return dict(value)
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f"{field} must be a table of positive integer seconds",
        )
    )
    return {}


def _profiles(value: object, warnings: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(
            _warning(
                "invalid_quality_runner_config_field",
                "quality_runner.profiles must be a table of profile tables",
            )
        )
        return {}

    profiles: dict[str, dict[str, Any]] = {}
    for name, item in value.items():
        if not isinstance(name, str) or not name or not isinstance(item, dict):
            _profile_warning(str(name), warnings)
            continue
        extends = item.get("extends")
        if extends != PROFILE_EXTENDS_DEFAULT:
            _profile_warning(name, warnings)
            continue
        profiles[name] = {
            "extends": extends,
            "required_capabilities": _string_list(
                item.get("required_capabilities"),
                f"quality_runner.profiles.{name}.required_capabilities",
                warnings,
            ),
            "required_capabilities_configured": "required_capabilities" in item,
            "allowed_package_managers": _string_list(
                item.get("allowed_package_managers"),
                f"quality_runner.profiles.{name}.allowed_package_managers",
                warnings,
            ),
        }
    return profiles


def _profile_warning(name: str, warnings: list[dict[str, str]]) -> None:
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f'quality_runner.profiles.{name} must be a table with extends = "default"',
        )
    )


def _gates(value: object, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(
            _warning(
                "invalid_quality_runner_config_field",
                "quality_runner.gates must be a list of tables",
            )
        )
        return []

    gates: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            _gate_warning(index, warnings)
            continue
        capability_id = item.get("id")
        command = item.get("command")
        ecosystem = item.get("ecosystem")
        source = item.get("source")
        owner = item.get("owner")
        required = item.get("required")
        severity = item.get("severity")
        mutating_risk = item.get("mutating_risk")
        if (
            isinstance(capability_id, str)
            and capability_id
            and isinstance(command, str)
            and command
            and isinstance(ecosystem, str)
            and ecosystem
            and isinstance(source, str)
            and source
            and isinstance(owner, str)
            and owner
            and isinstance(required, bool)
            and isinstance(severity, str)
            and severity
            and (mutating_risk is None or mutating_risk in {"safe", "unknown", "mutating"})
        ):
            gates.append(
                {
                    "id": capability_id,
                    "command": command,
                    "ecosystem": ecosystem,
                    "source": source,
                    "owner": owner,
                    "required": required,
                    "severity": severity,
                    **({"mutating_risk": mutating_risk} if mutating_risk is not None else {}),
                }
            )
        else:
            _gate_warning(index, warnings)
    return gates


def _gate_warning(index: int, warnings: list[dict[str, str]]) -> None:
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f"quality_runner.gates[{index}] must include id, command, ecosystem, source, owner, required, and severity; mutating_risk must be safe, unknown, or mutating when set",
        )
    )


def _accepted_exceptions(value: object, warnings: list[dict[str, str]]) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(
            _warning(
                "invalid_quality_runner_config_field",
                "quality_runner.accepted_exceptions must be a list of tables",
            )
        )
        return []

    accepted: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            _accepted_exception_warning(index, warnings)
            continue
        capability = item.get("capability")
        reason = item.get("reason")
        owner = item.get("owner")
        expires = item.get("expires")
        if (
            isinstance(capability, str)
            and capability
            and isinstance(reason, str)
            and reason
            and isinstance(owner, str)
            and owner
            and isinstance(expires, str)
            and expires
        ):
            accepted.append(
                dict(capability=capability, reason=reason, owner=owner, expires=expires)
            )
        else:
            _accepted_exception_warning(index, warnings)
    return accepted


def _accepted_dispositions(
    value: object,
    warnings: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(
            _warning(
                "invalid_quality_runner_config_field",
                "quality_runner.accepted_dispositions must be a list of tables",
            )
        )
        return []

    accepted: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            _accepted_disposition_warning(index, warnings)
            continue
        fingerprint = item.get("fingerprint")
        status = item.get("status")
        reason = item.get("reason")
        owner = item.get("owner")
        expires = item.get("expires")
        source_run_id = item.get("source_run_id")
        review_evidence = item.get("review_evidence")
        if (
            isinstance(fingerprint, str)
            and fingerprint
            and isinstance(status, str)
            and status in ACCEPTED_DISPOSITION_STATUSES
            and isinstance(reason, str)
            and reason
            and isinstance(owner, str)
            and owner
            and (expires is None or isinstance(expires, str))
            and (source_run_id is None or isinstance(source_run_id, str))
            and (
                review_evidence is None
                or (
                    isinstance(review_evidence, list)
                    and all(isinstance(entry, str) and entry for entry in review_evidence)
                )
            )
        ):
            accepted.append(
                {
                    "fingerprint": fingerprint,
                    "status": status,
                    "reason": reason,
                    "owner": owner,
                    **({"expires": expires} if isinstance(expires, str) and expires else {}),
                    **(
                        {"source_run_id": source_run_id}
                        if isinstance(source_run_id, str) and source_run_id
                        else {}
                    ),
                    **(
                        {"review_evidence": review_evidence}
                        if isinstance(review_evidence, list) and review_evidence
                        else {}
                    ),
                }
            )
        else:
            _accepted_disposition_warning(index, warnings)
    return accepted


def _accepted_disposition_warning(index: int, warnings: list[dict[str, str]]) -> None:
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f"quality_runner.accepted_dispositions[{index}] must include fingerprint, status, reason, owner, and optional expires strings",
        )
    )


def _accepted_exception_warning(index: int, warnings: list[dict[str, str]]) -> None:
    warnings.append(
        _warning(
            "invalid_quality_runner_config_field",
            f"quality_runner.accepted_exceptions[{index}] must include capability, reason, owner, and expires strings",
        )
    )


def _warning(code: str, message: str) -> dict[str, str]:
    return dict(code=code, message=message, path=CONFIG_FILE_NAME)
