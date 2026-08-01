from __future__ import annotations

import json
import re
import tomllib
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from quality_runner.schema_constants import RELEASE_EVIDENCE_SCHEMA

MAX_EVIDENCE_BYTES = 1_000_000
MAX_PROVENANCE_AGE = timedelta(hours=24)


def load_release_evidence(repo_root: Path, path: Path) -> tuple[dict[str, Any] | None, str | None]:
    root = repo_root.expanduser().resolve()
    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.absolute()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None, "release evidence file must be inside the target repository"
    if candidate.is_symlink():
        return None, "release evidence file must not be a symlink"
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root)
    except ValueError:
        return None, "release evidence file must resolve inside the target repository"
    if resolved != candidate:
        return None, "release evidence file must not traverse a symlinked path"
    if not candidate.exists():
        return None, f"release evidence file is missing: {candidate.relative_to(root)}"
    try:
        if candidate.stat().st_size > MAX_EVIDENCE_BYTES:
            return None, "release evidence file exceeds the size limit"
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"release evidence file could not be read: {error}"
    if not isinstance(payload, dict):
        return None, "release evidence file must contain a JSON object"
    payload_map = cast(dict[str, Any], payload)
    errors = validate_release_evidence(payload_map)
    return (payload_map, None) if not errors else (None, "; ".join(errors))


def validate_release_evidence(payload: object) -> list[str]:
    payload_map = _dict(payload)
    if payload_map is None:
        return ["release evidence file must contain a JSON object"]
    if payload_map.get("schema") != RELEASE_EVIDENCE_SCHEMA:
        return [f"release evidence schema must be {RELEASE_EVIDENCE_SCHEMA}"]
    errors: list[str] = []
    target = _dict(payload_map.get("target"))
    if target is None:
        errors.append("release evidence target is missing")
    else:
        for field in ("head_sha", "ref"):
            if not non_empty_string(target.get(field)):
                errors.append(f"release evidence target.{field} is required")
    if not non_empty_string(payload_map.get("release_version")):
        errors.append("release evidence release_version is required")
    owner = _dict(payload_map.get("owner"))
    if owner is None:
        errors.append("release evidence owner is missing")
    else:
        for field in ("name", "role"):
            if not non_empty_string(owner.get(field)):
                errors.append(f"release evidence owner.{field} is required")
    acceptance = payload_map.get("acceptance")
    if not isinstance(acceptance, list):
        errors.append("release evidence acceptance must be an array")
    else:
        if not acceptance:
            errors.append("release evidence acceptance must contain at least one decision")
        for index, item in enumerate(cast(list[Any], acceptance)):
            errors.extend(_decision_errors("acceptance", index, item, "accepted"))
    artifact = _dict(payload_map.get("artifact"))
    if artifact is None:
        errors.append("release evidence artifact is missing")
    else:
        for field in ("version", "source_head"):
            if not non_empty_string(artifact.get(field)):
                errors.append(f"release evidence artifact.{field} is required")
        if not valid_digest(artifact.get("digest")):
            errors.append("release evidence artifact.digest must be a SHA-256 digest")
        if "path" in artifact and not non_empty_string(artifact.get("path")):
            errors.append("release evidence artifact.path must be a non-empty string")
    errors.extend(_proof_collection_errors(payload_map, "migration", MIGRATION_PROOFS))
    errors.extend(_proof_collection_errors(payload_map, "publication", PUBLICATION_PROOFS))
    external_checks = payload_map.get("external_checks")
    if external_checks is not None and not isinstance(external_checks, list):
        errors.append("release evidence external_checks must be an array")
    elif isinstance(external_checks, list):
        for index, item in enumerate(cast(list[Any], external_checks)):
            errors.extend(_decision_errors("external_checks", index, item, "passed"))
    return errors


MIGRATION_PROOFS = ("forward", "rollback", "failure_injection", "reconciliation")
PUBLICATION_PROOFS = ("authorization", "sanitization", "immutability", "media_access")


def _proof_collection_errors(
    payload: dict[str, Any], collection: str, required_fields: tuple[str, ...]
) -> list[str]:
    raw_value = payload.get(collection)
    if raw_value is None:
        return []
    value = _dict(raw_value)
    if value is None:
        return [f"release evidence {collection} must be an object"]
    errors: list[str] = []
    for field in required_fields:
        proof = value.get(field)
        if proof is None:
            errors.append(f"release evidence {collection}.{field} is required")
        elif not _valid_proof(proof):
            errors.append(
                f"release evidence {collection}.{field} must be passed, blocked, or pending proof"
            )
    return errors


def _valid_proof(value: object) -> bool:
    if isinstance(value, str) and value in {"passed", "blocked", "pending"}:
        return True
    value_map = _dict(value)
    if value_map is None or value_map.get("status") not in {"passed", "blocked", "pending"}:
        return False
    evidence = value_map.get("evidence")
    evidence_items = cast(list[Any], evidence) if isinstance(evidence, list) else []
    return (
        isinstance(evidence, list)
        and bool(evidence_items)
        and all(non_empty_string(item) for item in evidence_items)
    )


def _decision_errors(
    collection: str,
    index: int,
    item: object,
    accepted_status: str,
) -> list[str]:
    prefix = f"release evidence {collection}[{index}]"
    item_map = _dict(item)
    if item_map is None:
        return [f"{prefix} must be an object"]
    errors: list[str] = []
    if not non_empty_string(item_map.get("id")):
        errors.append(f"{prefix}.id is required")
    statuses = {accepted_status, "blocked", "pending"}
    if item_map.get("status") not in statuses:
        errors.append(f"{prefix}.status must be {', '.join(sorted(statuses))}")
    evidence = item_map.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or not all(non_empty_string(value) for value in cast(list[Any], evidence))
    ):
        errors.append(f"{prefix}.evidence must be a non-empty string array")
    return errors


def detected_versions(repo_root: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for filename, section, key in (
        ("pyproject.toml", "project", "version"),
        ("Cargo.toml", "package", "version"),
    ):
        path = repo_root / filename
        if not path.is_file():
            continue
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        section_value = _dict(payload.get(section))
        if section_value is not None and isinstance(section_value.get(key), str):
            versions[f"{filename}:{section}.{key}"] = section_value[key]
    package_json = repo_root / "package.json"
    if package_json.is_file():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        payload_map = _dict(cast(object, payload))
        if payload_map is not None and isinstance(payload_map.get("version"), str):
            versions["package.json:version"] = cast(str, payload_map["version"])
    init_file = repo_root / "quality_runner" / "__init__.py"
    if init_file.is_file():
        try:
            text = init_file.read_text(encoding="utf-8")
        except OSError:
            text = ""
        match = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", text)
        if match:
            versions["quality_runner/__init__.py:__version__"] = match.group(1)
    version_file = repo_root / "quality_runner" / "_version.py"
    if version_file.is_file():
        try:
            text = version_file.read_text(encoding="utf-8")
        except OSError:
            text = ""
        match = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", text)
        if match:
            versions["quality_runner/_version.py:__version__"] = match.group(1)
    return versions


def fresh_provenance_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        captured = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if captured.tzinfo is None:
        return False
    now = datetime.now(UTC)
    return captured <= now + timedelta(minutes=5) and now - captured <= MAX_PROVENANCE_AGE


def non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_digest(value: object) -> bool:
    return (
        isinstance(value, str) and re.fullmatch(r"(?:sha256:)?[0-9a-fA-F]{64}", value) is not None
    )


def normalize_digest(value: object) -> str | None:
    return value.removeprefix("sha256:").lower() if isinstance(value, str) else None


def file_digest(path: Path) -> str | None:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _dict(value: object) -> dict[str, Any] | None:
    return cast(dict[str, Any], value) if isinstance(value, dict) else None
