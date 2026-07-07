from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from quality_runner.config import CONFIG_FILE_NAME, load_repo_config
from quality_runner.schema_constants import SKILL_INGEST_RESULT_SCHEMA
from quality_runner.skill_config import (
    FORBIDDEN_SKILL_FIELDS,
    _load_skill_pack,
    _resolve_skill_path,
    sanitize_skill_id,
)

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


def _canonical_skill_toml(raw: dict[str, Any], skill_id: str) -> str:
    lines = [
        f'id = "{skill_id}"',
        f'name = "{_escape_toml_string(str(raw.get("name", skill_id)))}"',
    ]
    version = raw.get("version")
    if isinstance(version, str) and version:
        lines.append(f'version = "{_escape_toml_string(version)}"')
    description = raw.get("description")
    if isinstance(description, str) and description:
        lines.append(f'description = "{_escape_toml_string(description)}"')
    lines.append("")

    deterministic_rules = raw.get("deterministic_rules")
    if isinstance(deterministic_rules, list):
        for rule in deterministic_rules:
            if not isinstance(rule, dict):
                continue
            lines.append("[[deterministic_rules]]")
            for key, value in rule.items():
                lines.extend(_toml_field_lines(key, value))
            lines.append("")

    agent_reviews = raw.get("agent_reviews")
    if isinstance(agent_reviews, list):
        for review in agent_reviews:
            if not isinstance(review, dict):
                continue
            lines.append("[[agent_reviews]]")
            for key, value in review.items():
                lines.extend(_toml_field_lines(key, value))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _toml_field_lines(key: str, value: object) -> list[str]:
    if isinstance(value, str):
        if "\n" in value:
            return [f'{key} = """', value.rstrip(), '"""']
        return [f'{key} = "{_escape_toml_string(value)}"']
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        quoted = ", ".join(f'"{_escape_toml_string(item)}"' for item in value)
        return [f"{key} = [{quoted}]"]
    return []


def _escape_toml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _update_repo_config(
    repo_root: Path,
    *,
    skill_id: str,
    skill_path: str,
    activate: bool,
) -> None:
    config_path = repo_root / CONFIG_FILE_NAME
    existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    config = load_repo_config(repo_root)
    skills_section = config.get("skills")
    if not isinstance(skills_section, dict):
        skills_section = {"enabled": True}

    local = skills_section.get("local")
    if not isinstance(local, list):
        local = []

    updated_local: list[dict[str, Any]] = []
    found = False
    for item in local:
        if isinstance(item, dict) and item.get("id") == skill_id:
            updated_local.append({"id": skill_id, "path": skill_path})
            found = True
        elif isinstance(item, dict):
            updated_local.append(item)
    if not found:
        updated_local.append({"id": skill_id, "path": skill_path})

    active = skills_section.get("active")
    active_ids: list[str]
    if isinstance(active, list):
        active_ids = [item for item in active if isinstance(item, str) and item]
    else:
        active_ids = []
    if activate and skill_id not in active_ids:
        active_ids.append(skill_id)

    block = _render_skills_config_block(enabled=True, active=active_ids, local=updated_local)
    if "[quality_runner.skills]" in existing:
        existing = _replace_skills_block(existing, block)
    else:
        existing = existing.rstrip() + ("\n\n" if existing.strip() else "") + block + "\n"
    config_path.write_text(existing, encoding="utf-8")


def _render_skills_config_block(
    *,
    enabled: bool,
    active: list[str],
    local: list[dict[str, Any]],
) -> str:
    lines = ["[quality_runner.skills]", f"enabled = {'true' if enabled else 'false'}"]
    if active:
        quoted = ", ".join(f'"{item}"' for item in sorted(active))
        lines.append(f"active = [{quoted}]")
    for item in local:
        skill_id = item.get("id")
        path = item.get("path")
        if not isinstance(skill_id, str) or not isinstance(path, str):
            continue
        lines.append("")
        lines.append("[[quality_runner.skills.local]]")
        lines.append(f'id = "{skill_id}"')
        lines.append(f'path = "{path}"')
        applies_to = item.get("applies_to")
        if isinstance(applies_to, list) and applies_to:
            quoted = ", ".join(f'"{value}"' for value in applies_to)
            lines.append(f"applies_to = [{quoted}]")
    return "\n".join(lines)


def _replace_skills_block(existing: str, block: str) -> str:
    lines = existing.splitlines()
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip() == "[quality_runner.skills]":
            result.append(block.rstrip())
            index += 1
            while index < len(lines):
                next_line = lines[index]
                if next_line.startswith("[") and not next_line.startswith(
                    "[[quality_runner.skills"
                ):
                    break
                if next_line.startswith("[[quality_runner.skills"):
                    index += 1
                    while index < len(lines) and not (
                        lines[index].startswith("[")
                        and not lines[index].startswith("[[quality_runner.skills")
                    ):
                        index += 1
                    continue
                index += 1
            continue
        result.append(line)
        index += 1
    return "\n".join(result).rstrip() + "\n"


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
