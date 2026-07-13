from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_runner.config import CONFIG_FILE_NAME, load_repo_config


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

    sources = raw.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            lines.append("[[sources]]")
            for key, value in source.items():
                lines.extend(_toml_field_lines(key, value))
            lines.append("")

    for collection_name in ("deterministic_rules", "agent_reviews"):
        collection = raw.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            lines.append(f"[[{collection_name}]]")
            for key, value in item.items():
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
    update_repo_skills_config(
        repo_root,
        entries=[{"id": skill_id, "path": skill_path}],
        activate_ids=[skill_id] if activate else [],
    )


def update_repo_skills_config(
    repo_root: Path,
    *,
    entries: list[dict[str, str]],
    activate_ids: list[str] | None = None,
    replace_active: bool = False,
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

    entry_by_id = {
        item["id"]: item
        for item in entries
        if isinstance(item.get("id"), str) and isinstance(item.get("path"), str)
    }
    updated_local: list[dict[str, Any]] = []
    found_ids: set[str] = set()
    for item in local:
        item_id = item.get("id") if isinstance(item, dict) else None
        if isinstance(item_id, str) and item_id in entry_by_id:
            replacement = dict(entry_by_id[item_id])
            if (
                isinstance(item, dict)
                and isinstance(item.get("applies_to"), list)
                and "applies_to" not in replacement
            ):
                replacement["applies_to"] = item["applies_to"]
            updated_local.append(replacement)
            found_ids.add(item_id)
        elif isinstance(item, dict):
            updated_local.append(item)
    for item_id, item in entry_by_id.items():
        if item_id not in found_ids:
            updated_local.append(item)

    active = skills_section.get("active")
    if replace_active:
        active_ids: list[str] = []
    elif isinstance(active, list):
        active_ids = [item for item in active if isinstance(item, str) and item]
    else:
        active_ids = []
    for skill_id in activate_ids or []:
        if skill_id not in active_ids:
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
