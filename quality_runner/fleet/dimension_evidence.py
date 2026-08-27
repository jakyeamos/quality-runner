from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from quality_runner.fleet.contracts import FRESHNESS_DAYS, MAX_DOCUMENT_BYTES, relative_path

EVIDENCE_SCHEMA = "quality-runner-environment-legibility/v1"
EVIDENCE_CONTRACT_PATHS = (
    ".agents/environment-legibility.json",
    ".context/environment-legibility.json",
    "docs/environment-legibility.json",
    "environment-legibility.json",
)
EVIDENCE_DIMENSIONS = frozenset(
    {
        "architecture_boundaries",
        "coding_conventions",
        "security_constraints",
        "failure_modes",
        "implementation_examples",
        "definition_of_done",
        "approval_gated_paths",
        "deployment_rollback",
    }
)
_AUTOMATION_FILES = frozenset(
    {
        ".circleci/config.yml",
        ".circleci/config.yaml",
        ".gitlab-ci.yml",
        ".gitlab-ci.yaml",
        ".github/CODEOWNERS",
        ".pre-commit-config.yaml",
        ".pre-commit-config.yml",
        "CODEOWNERS",
        "Jenkinsfile",
        "azure-pipelines.yml",
        "azure-pipelines.yaml",
    }
)


def load_dimension_evidence(root: Path, as_of: str) -> dict[str, Any]:
    """Load and validate a repository-owned environment-legibility evidence contract."""
    path = next(
        (root / relative for relative in EVIDENCE_CONTRACT_PATHS if (root / relative).is_file()),
        None,
    )
    if path is None:
        return {"status": "missing", "dimensions": {}}
    display_path = relative_path(root, path)
    try:
        if path.is_symlink():
            raise ValueError("contract path is a symlink")
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise ValueError("contract exceeds the bounded audit size")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return _invalid_contract(display_path, str(error))
    if not isinstance(payload, dict):
        return _invalid_contract(display_path, "contract root must be an object")
    payload = cast(dict[str, Any], payload)
    if payload.get("schema_version") != EVIDENCE_SCHEMA:
        return _invalid_contract(display_path, "schema_version is missing or unsupported")
    owner = payload.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        return _invalid_contract(display_path, "contract owner is missing")
    reviewed = _parse_date(payload.get("last_reviewed"))
    current = _parse_date(as_of)
    if reviewed is None or current is None:
        return _invalid_contract(display_path, "contract freshness is unknown")
    status = "stale" if current - reviewed > timedelta(days=FRESHNESS_DAYS) else "current"
    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, dict):
        return _invalid_contract(display_path, "dimensions must be an object")
    dimensions = cast(dict[str, Any], dimensions)
    return {
        "status": status,
        "path": display_path,
        "dimensions": dimensions,
    }


def assess_dimension_evidence(
    root: Path,
    contract: dict[str, Any],
    dimension: str,
) -> dict[str, Any] | None:
    """Return a conservative 2-4 assessment for one supported dimension."""
    if dimension not in EVIDENCE_DIMENSIONS:
        return None
    contract_status = contract.get("status")
    contract_path = str(contract.get("path", EVIDENCE_CONTRACT_PATHS[0]))
    dimensions = contract.get("dimensions")
    if contract_status == "missing":
        return None
    if contract_status == "invalid":
        raw_evidence = contract.get("evidence", [])
        evidence = (
            cast(list[dict[str, str]], raw_evidence) if isinstance(raw_evidence, list) else []
        )
        return _result(
            score=2,
            status="unknown",
            message="Structured evidence is present but the repository contract is invalid.",
            evidence=evidence,
        )
    if not isinstance(dimensions, dict) or dimension not in dimensions:
        return None
    dimensions = cast(dict[str, Any], dimensions)
    item = dimensions.get(dimension)
    if not isinstance(item, dict):
        return _incomplete(contract_path, "dimension entry must be an object")
    item = cast(dict[str, Any], item)

    evidence: list[dict[str, str]] = [
        {"path": contract_path, "detail": f"repository-owned {dimension} evidence contract"}
    ]
    problems: list[str] = []
    evidence_paths = _string_list(item.get("evidence"))
    if not evidence_paths:
        problems.append("evidence paths are missing")
    for value in evidence_paths:
        checked = _checked_file(root, value)
        if checked is None:
            problems.append(f"evidence path is missing or unsafe: {value}")
        else:
            evidence.append({"path": value, "detail": "referenced repository evidence"})

    validation = item.get("validation")
    if not isinstance(validation, list) or not validation:
        problems.append("validation assertions are missing")
    else:
        for entry in _object_list(cast(object, validation)):
            result = _validate_assertion(root, entry, automation=False)
            if isinstance(result, str):
                problems.append(result)
            else:
                evidence.append(result)

    automation = item.get("automation")
    automated = False
    if automation is not None and not isinstance(automation, list):
        problems.append("automation assertions must be a list")
    elif isinstance(automation, list) and automation:
        automated = True
        for entry in _object_list(cast(object, automation)):
            result = _validate_assertion(root, entry, automation=True)
            if isinstance(result, str):
                problems.append(result)
            else:
                evidence.append(result)

    if contract_status == "stale":
        return _result(
            score=2,
            status="stale",
            message="Structured evidence exists, but its repository review is stale.",
            evidence=evidence[:15]
            + [{"path": contract_path, "detail": "last_reviewed exceeds the freshness window"}],
        )
    if problems:
        return _result(
            score=2,
            status="unknown",
            message=f"Structured evidence is incomplete: {'; '.join(problems[:3])}.",
            evidence=evidence[:12]
            + [{"path": contract_path, "detail": problem} for problem in problems[:4]],
        )
    if automated:
        return _result(
            score=4,
            status="maintained",
            message="Current repository evidence is validated and connected to an enforced surface.",
            evidence=evidence[:16],
        )
    return _result(
        score=3,
        status="validated",
        message="Current repository evidence and its validation assertions are verifiable.",
        evidence=evidence[:16],
    )


def _validate_assertion(
    root: Path,
    entry: object,
    *,
    automation: bool,
) -> dict[str, str] | str:
    label = "automation" if automation else "validation"
    if not isinstance(entry, dict):
        return f"{label} assertion must be an object"
    entry = cast(dict[str, Any], entry)
    value = entry.get("path")
    terms = _string_list(entry.get("contains"))
    if not isinstance(value, str) or not value.strip():
        return f"{label} assertion path is missing"
    if not terms:
        return f"{label} assertion contains terms are missing: {value}"
    path = _checked_file(root, value)
    if path is None:
        return f"{label} path is missing or unsafe: {value}"
    if automation and not _is_automation_surface(value):
        return f"automation path is not an enforcement surface: {value}"
    try:
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            return f"{label} path exceeds the bounded audit size: {value}"
        content = path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return f"{label} path could not be read: {value}"
    missing = [term for term in terms if term.lower() not in content]
    if missing:
        return f"{label} assertion did not match {value}: {', '.join(missing[:3])}"
    return {
        "path": value,
        "detail": f"{label} assertion matched: {', '.join(terms[:4])}",
    }


def _checked_file(root: Path, value: str) -> Path | None:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    if candidate.is_symlink() or not resolved.is_file():
        return None
    return resolved


def _is_automation_surface(value: str) -> bool:
    path = Path(value).as_posix()
    return path in _AUTOMATION_FILES or (
        path.startswith(".github/workflows/") and Path(path).suffix in {".yml", ".yaml"}
    )


def _invalid_contract(path: str, detail: str) -> dict[str, Any]:
    return {
        "status": "invalid",
        "path": path,
        "dimensions": {},
        "evidence": [{"path": path, "detail": detail}],
    }


def _incomplete(path: str, detail: str) -> dict[str, Any]:
    return _result(
        score=2,
        status="unknown",
        message="Structured evidence is present but its dimension entry is invalid.",
        evidence=[{"path": path, "detail": detail}],
    )


def _result(
    *, score: int, status: str, message: str, evidence: list[dict[str, str]]
) -> dict[str, Any]:
    return {"score": score, "status": status, "message": message, "evidence": evidence}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    values = cast(list[object], value)
    return [item for item in values if isinstance(item, str) and item.strip()]


def _object_list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _parse_date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{value}T00:00:00+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
