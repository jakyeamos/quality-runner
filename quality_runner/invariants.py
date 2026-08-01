from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, cast

from quality_runner.bug_learning import required_promotion_blocker

INVARIANT_REPORT_SCHEMA = "quality-runner-invariant-verification-v0.1"
INVARIANT_EVIDENCE_SCHEMA = "quality-runner-invariant-evidence-v0.1"
INVARIANT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ENFORCEMENT_VALUES = {"advisory", "required"}
MUTATING_RISK_VALUES = {"safe", "unknown", "mutating"}
EVIDENCE_STATUSES = {"passed", "failed", "blocked"}
BLOCKING_FAILURE_TYPES = {
    "environment-restricted",
    "dependency-setup-blocker",
    "read-only-mutation",
}


def parse_invariants(value: object, warnings: list[dict[str, str]]) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(_warning("quality_runner.invariants must be a list of tables"))
        return []

    typed_value = cast(list[Any], value)
    invariants: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(typed_value):
        parsed = _parse_invariant(item, index=index, warnings=warnings)
        if parsed is None:
            continue
        invariant_id = parsed["id"]
        if invariant_id in seen_ids:
            warnings.append(
                _warning(f"quality_runner.invariants[{index}].id duplicates {invariant_id!r}")
            )
            continue
        seen_ids.add(invariant_id)
        invariants.append(parsed)
    return invariants


def add_invariant_capabilities(
    *,
    scan: dict[str, Any],
    standards_packet: dict[str, Any],
    available: list[dict[str, Any]],
    missing: list[dict[str, Any]],
) -> None:
    repo_root = _repo_root(scan, standards_packet)
    for invariant in configured_invariants(standards_packet):
        promotion_blocker = required_promotion_blocker(repo_root, invariant)
        if promotion_blocker is not None:
            missing.append(
                {
                    "id": invariant["id"],
                    "type": "invariant",
                    "reason": promotion_blocker,
                    "language": invariant["ecosystem"],
                    "owner": invariant["owner"],
                    "required_by": "candidate-promotion-contract",
                }
            )
            continue
        missing_surfaces = _missing_surfaces(repo_root, invariant)
        if missing_surfaces:
            if invariant["enforcement"] == "required":
                missing.append(
                    {
                        "id": invariant["id"],
                        "type": "invariant",
                        "reason": f"proof surfaces are missing: {', '.join(missing_surfaces)}",
                        "language": invariant["ecosystem"],
                        "owner": invariant["owner"],
                        "required_by": "repository-invariant",
                    }
                )
            continue
        command = invariant.get("command")
        if not isinstance(command, str) or not command:
            continue
        available.append(
            {
                "id": invariant["id"],
                "type": "command",
                "capability_kind": "semantic_invariant",
                "source": ".quality-runner.toml:quality_runner.invariants",
                "command": command,
                "language": invariant["ecosystem"],
                "owner": invariant["owner"],
                "severity": (
                    "blocker" if invariant["enforcement"] == "required" else "observation"
                ),
                "mutating_risk": invariant["mutating_risk"],
                "enforcement": invariant["enforcement"],
                "description": invariant["description"],
                "surfaces": list(invariant["surfaces"]),
                **_optional("candidate_id", invariant.get("candidate_id")),
                **_optional("promotion_receipt", invariant.get("promotion_receipt")),
                **(
                    {"required_by": "repository-invariant"}
                    if invariant["enforcement"] == "required"
                    else {}
                ),
                "verification_state": {
                    "discovery": "command-discovered",
                    "execution": "not-run",
                    "result": "unknown",
                },
            }
        )


def configured_invariants(standards_packet: dict[str, Any]) -> list[dict[str, Any]]:
    config = _dict(standards_packet.get("config"))
    if config is None:
        return []
    invariants = config.get("invariants")
    if not isinstance(invariants, list):
        return []
    return _dict_list(cast(object, invariants))


def build_invariant_report(
    *,
    repo_root: Path,
    config: dict[str, Any],
    gate_verification: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    checked_at = _utc_now(now)
    gates = _gate_results(gate_verification)
    configured = config.get("invariants")
    invariants = _dict_list(cast(object, configured))
    results = [
        _invariant_result(
            repo_root=repo_root,
            invariant=invariant,
            gate=gates.get(str(invariant.get("id"))),
            checked_at=checked_at,
        )
        for invariant in invariants
    ]
    counts = {
        status: sum(1 for result in results if result["status"] == status)
        for status in ("passed", "failed", "blocked", "unknown", "stale")
    }
    return {
        "schema": INVARIANT_REPORT_SCHEMA,
        "checked_at": checked_at.isoformat().replace("+00:00", "Z"),
        "status": _report_status(results),
        "summary": {"total": len(results), **counts},
        "invariants": results,
    }


def apply_invariant_status(
    gate_verification: dict[str, Any],
    invariant_report: dict[str, Any],
) -> dict[str, Any]:
    status = gate_verification.get("status")
    required = [
        item
        for item in _dict_list(invariant_report.get("invariants", []))
        if item.get("enforcement") == "required"
    ]
    if any(item.get("status") == "failed" for item in required):
        status = "failed"
    elif any(item.get("status") in {"blocked", "unknown", "stale"} for item in required):
        status = "blocked"
    return {
        **gate_verification,
        "status": status,
        "invariant_verification": {
            "schema": invariant_report.get("schema"),
            "status": invariant_report.get("status"),
            "summary": invariant_report.get("summary"),
        },
    }


def _parse_invariant(
    value: object,
    *,
    index: int,
    warnings: list[dict[str, str]],
) -> dict[str, Any] | None:
    field = f"quality_runner.invariants[{index}]"
    value_map = _dict(value)
    if value_map is None:
        warnings.append(_warning(f"{field} must be a table"))
        return None

    invariant_id = value_map.get("id")
    description = value_map.get("description")
    owner = value_map.get("owner")
    surfaces = value_map.get("surfaces")
    command = value_map.get("command")
    evidence_file = value_map.get("evidence_file")
    enforcement = value_map.get("enforcement", "advisory")
    ecosystem = value_map.get("ecosystem", "repository")
    mutating_risk = value_map.get("mutating_risk", "unknown")
    freshness_days = value_map.get("freshness_days", 30)
    candidate_id = value_map.get("candidate_id")
    promotion_receipt = value_map.get("promotion_receipt")

    valid = True
    if not isinstance(invariant_id, str) or not INVARIANT_ID_RE.fullmatch(invariant_id):
        valid = False
    if not isinstance(description, str) or not description:
        valid = False
    if not isinstance(owner, str) or not owner:
        valid = False
    if not _relative_path_list(surfaces):
        valid = False
    if command is not None and (not isinstance(command, str) or not command):
        valid = False
    if evidence_file is not None and (
        not isinstance(evidence_file, str) or not _safe_relative_path(evidence_file)
    ):
        valid = False
    if not command and not evidence_file:
        valid = False
    if enforcement not in ENFORCEMENT_VALUES:
        valid = False
    if not isinstance(ecosystem, str) or not ecosystem:
        valid = False
    if mutating_risk not in MUTATING_RISK_VALUES:
        valid = False
    if (
        not isinstance(freshness_days, int)
        or isinstance(freshness_days, bool)
        or freshness_days <= 0
    ):
        valid = False
    if candidate_id is not None and (
        not isinstance(candidate_id, str) or not INVARIANT_ID_RE.fullmatch(candidate_id)
    ):
        valid = False
    if promotion_receipt is not None and (
        not isinstance(promotion_receipt, str) or not _safe_relative_path(promotion_receipt)
    ):
        valid = False
    if not valid:
        warnings.append(
            _warning(
                f"{field} must include a kebab-case id, description, owner, safe relative "
                "surfaces, and command or evidence_file; enforcement must be advisory or "
                "required, mutating_risk must be safe, unknown, or mutating, and "
                "freshness_days must be a positive integer; candidate_id must be kebab-case "
                "and promotion_receipt must be a safe relative path when supplied"
            )
        )
        return None

    surfaces = cast(list[str], surfaces)
    return {
        "id": invariant_id,
        "description": description,
        "owner": owner,
        "surfaces": list(surfaces),
        **({"command": command} if isinstance(command, str) else {}),
        **({"evidence_file": evidence_file} if isinstance(evidence_file, str) else {}),
        "enforcement": enforcement,
        "ecosystem": ecosystem,
        "mutating_risk": mutating_risk,
        "freshness_days": freshness_days,
        **({"candidate_id": candidate_id} if isinstance(candidate_id, str) else {}),
        **({"promotion_receipt": promotion_receipt} if isinstance(promotion_receipt, str) else {}),
    }


def _invariant_result(
    *,
    repo_root: Path,
    invariant: dict[str, Any],
    gate: dict[str, Any] | None,
    checked_at: datetime,
) -> dict[str, Any]:
    invariant_id = str(invariant.get("id") or "unknown")
    base = {
        "id": invariant_id,
        "description": invariant.get("description"),
        "owner": invariant.get("owner"),
        "enforcement": invariant.get("enforcement", "advisory"),
        "surfaces": list(invariant.get("surfaces", [])),
        **_optional("candidate_id", invariant.get("candidate_id")),
    }
    promotion_blocker = required_promotion_blocker(repo_root, invariant)
    if promotion_blocker is not None:
        return {
            **base,
            "status": "blocked",
            "reason": promotion_blocker,
            "source": str(invariant.get("promotion_receipt") or "promotion-receipt"),
        }
    missing_surfaces = _missing_surfaces(repo_root, invariant)
    if missing_surfaces:
        return {
            **base,
            "status": "unknown",
            "reason": "configured proof surfaces are missing",
            "missing_surfaces": missing_surfaces,
        }

    if gate is not None:
        gate_status = gate.get("status")
        if gate_status == "passed":
            return {**base, "status": "passed", "source": "current-run"}
        if gate_status == "failed":
            status = "blocked" if gate.get("failure_type") in BLOCKING_FAILURE_TYPES else "failed"
            return {
                **base,
                "status": status,
                "source": "current-run",
                **_optional("failure_type", gate.get("failure_type")),
                **_optional("reason", gate.get("reason")),
            }

    evidence = _evidence_result(repo_root, invariant, checked_at)
    if evidence is not None:
        return {**base, **evidence}
    return {
        **base,
        "status": "unknown",
        "reason": (
            "verification command was not executed and no usable evidence file was available"
        ),
    }


def _evidence_result(
    repo_root: Path,
    invariant: dict[str, Any],
    checked_at: datetime,
) -> dict[str, Any] | None:
    relative = invariant.get("evidence_file")
    if not isinstance(relative, str):
        return None
    path = repo_root / relative
    if not path.is_file():
        return {
            "status": "unknown",
            "source": relative,
            "reason": "configured invariant evidence file is missing",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "unknown",
            "source": relative,
            "reason": "configured invariant evidence file is unreadable or invalid JSON",
        }
    payload_map = _dict(payload)
    if payload_map is None:
        return {
            "status": "unknown",
            "source": relative,
            "reason": "configured invariant evidence file must contain an object",
        }
    if (
        payload_map.get("schema") != INVARIANT_EVIDENCE_SCHEMA
        or payload_map.get("id") != invariant["id"]
    ):
        return {
            "status": "unknown",
            "source": relative,
            "reason": "configured invariant evidence schema or id does not match",
        }
    evidence_status = payload_map.get("status")
    evidence_time = _parse_timestamp(payload_map.get("checked_at"))
    if evidence_status not in EVIDENCE_STATUSES or evidence_time is None:
        return {
            "status": "unknown",
            "source": relative,
            "reason": "configured invariant evidence status or checked_at is invalid",
        }
    max_age = timedelta(days=int(invariant.get("freshness_days", 30)))
    if checked_at - evidence_time > max_age:
        return {
            "status": "stale",
            "source": relative,
            "evidence_status": evidence_status,
            "evidence_checked_at": evidence_time.isoformat().replace("+00:00", "Z"),
            "reason": "configured invariant evidence is older than freshness_days",
        }
    return {
        "status": evidence_status,
        "source": relative,
        "evidence_checked_at": evidence_time.isoformat().replace("+00:00", "Z"),
    }


def _missing_surfaces(repo_root: Path, invariant: dict[str, Any]) -> list[str]:
    surfaces = invariant.get("surfaces")
    if not isinstance(surfaces, list):
        return []
    return [
        surface
        for surface in cast(list[Any], surfaces)
        if isinstance(surface, str) and not (repo_root / surface).exists()
    ]


def _gate_results(gate_verification: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(gate_verification, dict):
        return {}
    gates = gate_verification.get("gates")
    if not isinstance(gates, list):
        return {}
    return {
        str(gate["id"]): gate
        for gate in _dict_list(cast(object, gates))
        if isinstance(gate.get("id"), str)
    }


def _report_status(results: list[dict[str, Any]]) -> str:
    required = [result for result in results if result.get("enforcement") == "required"]
    if any(result["status"] == "failed" for result in required):
        return "failed"
    if any(result["status"] == "blocked" for result in required):
        return "blocked"
    if any(result["status"] == "stale" for result in required):
        return "stale"
    if any(result["status"] == "unknown" for result in required):
        return "unknown"
    if results and all(result["status"] == "passed" for result in results):
        return "passed"
    return "passed"


def _repo_root(scan: dict[str, Any], standards_packet: dict[str, Any]) -> Path:
    raw = scan.get("repo_root") or standards_packet.get("repo_root") or "."
    return Path(str(raw)).expanduser().resolve()


def _relative_path_list(value: object) -> bool:
    if not isinstance(value, list):
        return False
    typed_value = cast(list[Any], value)
    return bool(typed_value) and all(
        isinstance(item, str) and _safe_relative_path(item) for item in typed_value
    )


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _dict(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def _dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in cast(list[Any], value) if isinstance(item, dict)]


def _utc_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("invariant verification time must be timezone-aware")
    return value.astimezone(UTC)


def _optional(key: str, value: object) -> dict[str, Any]:
    return {} if value is None else {key: value}


def _warning(message: str) -> dict[str, str]:
    return {
        "code": "invalid_quality_runner_config_field",
        "message": message,
        "path": ".quality-runner.toml",
    }
