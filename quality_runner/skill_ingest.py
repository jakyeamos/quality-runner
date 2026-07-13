from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from quality_runner.config import CONFIG_FILE_NAME
from quality_runner.schema_constants import SKILL_APPEND_RESULT_SCHEMA, SKILL_INGEST_RESULT_SCHEMA
from quality_runner.skill_config import (
    FORBIDDEN_SKILL_FIELDS,
    _load_skill_pack,
    _resolve_skill_path,
    sanitize_skill_id,
)
from quality_runner.skill_registration import _canonical_skill_toml, _update_repo_config

SKILLS_DIR = ".quality-runner/skills"


def validate_skill_pack(
    candidate_path: Path,
    *,
    skill_id: str,
    repo_root: Path,
) -> dict[str, Any]:
    normalized_id = sanitize_skill_id(skill_id)
    if normalized_id is None:
        return _result(
            status="rejected",
            write=False,
            skill_id=skill_id,
            active=False,
            warnings=[],
            errors=[f"invalid skill id: {skill_id}"],
        )

    if not candidate_path.exists():
        return _result(
            status="rejected",
            write=False,
            skill_id=normalized_id,
            active=False,
            warnings=[],
            errors=[f"candidate skill file not found: {candidate_path}"],
        )

    try:
        raw = tomllib.loads(candidate_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        return _result(
            status="rejected",
            write=False,
            skill_id=normalized_id,
            active=False,
            warnings=[],
            errors=[f"candidate skill file could not be parsed: {error}"],
        )

    if not isinstance(raw, dict):
        return _result(
            status="rejected",
            write=False,
            skill_id=normalized_id,
            active=False,
            warnings=[],
            errors=["candidate skill file must be a TOML table"],
        )

    for field in FORBIDDEN_SKILL_FIELDS:
        if field in raw:
            return _result(
                status="rejected",
                write=False,
                skill_id=normalized_id,
                active=False,
                warnings=[],
                errors=[f"candidate skill file contains forbidden field: {field}"],
            )

    file_id = raw.get("id")
    if isinstance(file_id, str) and file_id and sanitize_skill_id(file_id) != normalized_id:
        return _result(
            status="rejected",
            write=False,
            skill_id=normalized_id,
            active=False,
            warnings=[],
            errors=[f"skill id mismatch: --id {normalized_id} but file declares {file_id}"],
        )

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        return _result(
            status="rejected",
            write=False,
            skill_id=normalized_id,
            active=False,
            warnings=[],
            errors=["candidate skill file must include a non-empty name"],
        )

    skill_pack, warning = _load_skill_pack(candidate_path, normalized_id)

    warnings: list[str] = []
    if warning is not None:
        warnings.append(warning["message"])

    if skill_pack is None:
        return _result(
            status="rejected",
            write=False,
            skill_id=normalized_id,
            active=False,
            warnings=warnings,
            errors=["candidate skill pack failed validation"],
        )

    validation_warnings = skill_pack.get("validation_warnings")
    if isinstance(validation_warnings, list):
        warnings.extend(
            str(item["message"])
            for item in validation_warnings
            if isinstance(item, dict) and isinstance(item.get("message"), str)
        )

    return _result(
        status="validated",
        write=False,
        skill_id=normalized_id,
        active=False,
        warnings=warnings,
        errors=[],
        canonical_content=_canonical_skill_toml(raw, normalized_id),
    )


def ingest_skill_pack(
    candidate_path: Path,
    *,
    skill_id: str,
    repo_root: Path,
    activate: bool = False,
    write: bool = False,
) -> dict[str, Any]:
    validation = validate_skill_pack(candidate_path, skill_id=skill_id, repo_root=repo_root)
    if validation.get("status") == "rejected":
        return validation

    normalized_id = str(validation["skill_id"])
    skill_relative_path = f"{SKILLS_DIR}/{normalized_id}.toml"
    resolved_target, path_warning = _resolve_skill_path(repo_root, skill_relative_path)
    if path_warning is not None or resolved_target is None:
        return _result(
            status="rejected",
            write=False,
            skill_id=normalized_id,
            active=False,
            warnings=validation.get("warnings", []),
            errors=["skill target path rejected for traversal safety"],
        )

    canonical_content = validation.get("canonical_content")
    if not isinstance(canonical_content, str):
        return _result(
            status="rejected",
            write=False,
            skill_id=normalized_id,
            active=False,
            warnings=validation.get("warnings", []),
            errors=["canonical skill content unavailable"],
        )

    if not write:
        return _result(
            status="validated",
            write=False,
            skill_id=normalized_id,
            active=activate,
            warnings=validation.get("warnings", []),
            errors=[],
        )

    resolved_target.parent.mkdir(parents=True, exist_ok=True)
    resolved_target.write_text(canonical_content, encoding="utf-8")
    _update_repo_config(
        repo_root, skill_id=normalized_id, skill_path=skill_relative_path, activate=activate
    )

    return _result(
        status="registered",
        write=True,
        skill_id=normalized_id,
        active=activate,
        warnings=validation.get("warnings", []),
        errors=[],
    )


def append_skill_to_target(
    candidate_path: Path,
    *,
    source_skill_id: str,
    pack_id: str,
    target_path: Path,
    source_ref: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    return _append_skill_to_target(
        candidate_path,
        source_skill_id=source_skill_id,
        pack_id=pack_id,
        target_path=target_path,
        target_relative_path=None,
        repo_root=None,
        source_ref=source_ref,
        activate=False,
        write=write,
    )


def _append_skill_to_target(
    candidate_path: Path,
    *,
    source_skill_id: str,
    pack_id: str,
    target_path: Path,
    target_relative_path: str | None,
    repo_root: Path | None,
    source_ref: str | None,
    activate: bool,
    write: bool,
) -> dict[str, Any]:
    normalized_source_id = sanitize_skill_id(source_skill_id)
    normalized_pack_id = sanitize_skill_id(pack_id)
    if normalized_source_id is None or normalized_pack_id is None:
        return _append_result(
            status="rejected",
            write=False,
            source_skill_id=source_skill_id,
            pack_id=pack_id,
            active=False,
            warnings=[],
            errors=["source skill id and pack id must be valid skill ids"],
        )

    validation = validate_skill_pack(
        candidate_path,
        skill_id=normalized_source_id,
        repo_root=candidate_path.parent,
    )
    if validation.get("status") == "rejected":
        return _append_result(
            status="rejected",
            write=False,
            source_skill_id=normalized_source_id,
            pack_id=normalized_pack_id,
            active=False,
            warnings=validation.get("warnings", []),
            errors=validation.get("errors", []),
        )

    target_path = target_path.expanduser().resolve()
    if not target_path.exists():
        return _append_result(
            status="rejected",
            write=False,
            source_skill_id=normalized_source_id,
            pack_id=normalized_pack_id,
            active=False,
            warnings=validation.get("warnings", []),
            errors=[f"target pack not found: {normalized_pack_id}"],
        )

    target_pack, target_warning = _load_skill_pack(target_path, normalized_pack_id)
    warnings = list(validation.get("warnings", []))
    if target_warning is not None:
        warnings.append(target_warning["message"])
    if target_pack is None:
        return _append_result(
            status="rejected",
            write=False,
            source_skill_id=normalized_source_id,
            pack_id=normalized_pack_id,
            active=False,
            warnings=warnings,
            errors=["target pack failed validation"],
        )

    existing_sources = target_pack.get("sources")
    if isinstance(existing_sources, list) and any(
        isinstance(source, dict) and source.get("id") == normalized_source_id
        for source in existing_sources
    ):
        return _append_result(
            status="rejected",
            write=False,
            source_skill_id=normalized_source_id,
            pack_id=normalized_pack_id,
            active=False,
            warnings=warnings,
            errors=[f"source skill already appended to pack: {normalized_source_id}"],
        )

    candidate_path = candidate_path.expanduser().resolve()
    candidate_pack, candidate_warning = _load_skill_pack(candidate_path, normalized_source_id)
    if candidate_warning is not None:
        warnings.append(candidate_warning["message"])
    if candidate_pack is None:
        return _append_result(
            status="rejected",
            write=False,
            source_skill_id=normalized_source_id,
            pack_id=normalized_pack_id,
            active=False,
            warnings=warnings,
            errors=["candidate pack failed validation"],
        )

    merged_rules = list(target_pack.get("deterministic_rules", []))
    appended_rules = _namespace_pack_items(
        candidate_pack.get("deterministic_rules", []),
        source_id=normalized_source_id,
    )
    existing_rule_ids = {
        str(rule["id"])
        for rule in merged_rules
        if isinstance(rule, dict) and isinstance(rule.get("id"), str)
    }
    rule_collisions = sorted(
        str(rule["id"])
        for rule in appended_rules
        if isinstance(rule, dict)
        and isinstance(rule.get("id"), str)
        and rule["id"] in existing_rule_ids
    )
    if rule_collisions:
        return _append_result(
            status="rejected",
            write=False,
            source_skill_id=normalized_source_id,
            pack_id=normalized_pack_id,
            active=False,
            warnings=warnings,
            errors=[f"namespaced rule ids already exist: {', '.join(rule_collisions)}"],
        )
    merged_rules.extend(appended_rules)
    merged_reviews = list(target_pack.get("agent_reviews", []))
    appended_reviews = _namespace_pack_items(
        candidate_pack.get("agent_reviews", []), source_id=normalized_source_id
    )
    existing_review_ids = {
        str(review["id"])
        for review in merged_reviews
        if isinstance(review, dict) and isinstance(review.get("id"), str)
    }
    review_collisions = sorted(
        str(review["id"])
        for review in appended_reviews
        if isinstance(review, dict)
        and isinstance(review.get("id"), str)
        and review["id"] in existing_review_ids
    )
    if review_collisions:
        return _append_result(
            status="rejected",
            write=False,
            source_skill_id=normalized_source_id,
            pack_id=normalized_pack_id,
            active=False,
            warnings=warnings,
            errors=[f"namespaced review ids already exist: {', '.join(review_collisions)}"],
        )
    merged_reviews.extend(appended_reviews)
    sources = [
        source
        for source in target_pack.get("sources", [])
        if isinstance(source, dict) and isinstance(source.get("id"), str)
    ]
    source: dict[str, Any] = {"id": normalized_source_id}
    if source_ref:
        source["ref"] = source_ref
    candidate_version = candidate_pack.get("version")
    if isinstance(candidate_version, str) and candidate_version:
        source["version"] = candidate_version
    sources.append(source)
    canonical_content = _canonical_skill_toml(
        {
            "name": target_pack["name"],
            "version": target_pack.get("version"),
            "description": target_pack.get("description"),
            "sources": sources,
            "deterministic_rules": merged_rules,
            "agent_reviews": merged_reviews,
        },
        normalized_pack_id,
    )

    if not write:
        return _append_result(
            status="validated",
            write=False,
            source_skill_id=normalized_source_id,
            pack_id=normalized_pack_id,
            active=activate,
            warnings=warnings,
            errors=[],
        )

    target_path.write_text(canonical_content, encoding="utf-8")
    if repo_root is not None and target_relative_path is not None:
        _update_repo_config(
            repo_root,
            skill_id=normalized_pack_id,
            skill_path=target_relative_path,
            activate=activate,
        )
    return _append_result(
        status="appended",
        write=True,
        source_skill_id=normalized_source_id,
        pack_id=normalized_pack_id,
        active=activate,
        warnings=warnings,
        errors=[],
    )


def _namespace_pack_items(value: object, *, source_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    namespaced: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        item_id = copied.get("id")
        if isinstance(item_id, str) and item_id:
            copied["id"] = f"{source_id}/{item_id}"
        namespaced.append(copied)
    return namespaced


def _result(
    *,
    status: str,
    write: bool,
    skill_id: str,
    active: bool,
    warnings: list[str] | list[dict[str, str]],
    errors: list[str],
    canonical_content: str | None = None,
) -> dict[str, Any]:
    normalized_warnings = [
        warning if isinstance(warning, str) else str(warning.get("message", warning))
        for warning in warnings
    ]
    payload: dict[str, Any] = {
        "schema": SKILL_INGEST_RESULT_SCHEMA,
        "status": status,
        "write": write,
        "skill_id": skill_id,
        "skill_path": f"{SKILLS_DIR}/{skill_id}.toml",
        "config_path": CONFIG_FILE_NAME,
        "active": active,
        "warnings": normalized_warnings,
        "errors": errors,
    }
    if canonical_content is not None:
        payload["canonical_content"] = canonical_content
    return payload


def _append_result(
    *,
    status: str,
    write: bool,
    source_skill_id: str,
    pack_id: str,
    active: bool,
    warnings: list[str] | list[dict[str, str]],
    errors: list[str],
) -> dict[str, Any]:
    normalized_warnings = [
        warning if isinstance(warning, str) else str(warning.get("message", warning))
        for warning in warnings
    ]
    return {
        "schema": SKILL_APPEND_RESULT_SCHEMA,
        "status": status,
        "write": write,
        "source_skill_id": source_skill_id,
        "pack_id": pack_id,
        "skill_path": f"{SKILLS_DIR}/{pack_id}.toml",
        "config_path": CONFIG_FILE_NAME,
        "active": active,
        "warnings": normalized_warnings,
        "errors": errors,
    }
