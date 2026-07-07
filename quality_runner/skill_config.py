from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

FORBIDDEN_SKILL_FIELDS = frozenset(
    {
        "exec",
        "execute",
        "script",
        "command",
        "shell",
        "python",
        "javascript",
        "code",
        "run",
        "plugin",
    }
)


def load_active_skills(
    repo_root: Path,
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    section = config.get("skills")
    if not isinstance(section, dict) or section.get("enabled") is not True:
        return [], []

    root = repo_root.expanduser().resolve()
    local_entries = section.get("local")
    if not isinstance(local_entries, list) or not local_entries:
        return [], []

    active_ids = _active_skill_ids(section)
    skills: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []

    for entry in local_entries:
        if not isinstance(entry, dict):
            continue
        skill_id = entry.get("id")
        skill_path = entry.get("path")
        if not isinstance(skill_id, str) or not skill_id:
            continue
        if active_ids is not None and skill_id not in active_ids:
            continue
        if not isinstance(skill_path, str) or not skill_path:
            warnings.append(_skill_warning(skill_id, "skill path is missing or invalid"))
            continue

        resolved_path, path_warning = _resolve_skill_path(root, skill_path)
        if path_warning is not None:
            warnings.append(path_warning)
            continue
        if resolved_path is None or not resolved_path.exists():
            warnings.append(_skill_warning(skill_id, f"skill file not found: {skill_path}"))
            continue

        skill_pack, load_warning = _load_skill_pack(resolved_path, skill_id)
        if load_warning is not None:
            warnings.append(load_warning)
            continue
        if skill_pack is None:
            continue

        applies_to = entry.get("applies_to")
        if isinstance(applies_to, list):
            patterns = [item for item in applies_to if isinstance(item, str) and item]
            if patterns:
                skill_pack["applies_to"] = patterns

        skills.append(skill_pack)

    return skills, warnings


def _active_skill_ids(section: dict[str, Any]) -> set[str] | None:
    active = section.get("active")
    if active is None:
        return None
    if not isinstance(active, list):
        return set()
    return {item for item in active if isinstance(item, str) and item}


def _resolve_skill_path(
    repo_root: Path,
    skill_path: str,
) -> tuple[Path | None, dict[str, str] | None]:
    normalized = skill_path.strip().replace("\\", "/")
    if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
        return None, _skill_warning(
            "unknown", f"skill path rejected for traversal safety: {skill_path}"
        )

    candidate = (repo_root / normalized).resolve()
    try:
        candidate.relative_to(repo_root)
    except ValueError:
        return None, _skill_warning("unknown", f"skill path must stay inside repo: {skill_path}")

    return candidate, None


def _load_skill_pack(
    path: Path, configured_id: str
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        return None, _skill_warning(configured_id, f"skill file could not be parsed: {error}")

    if not isinstance(payload, dict):
        return None, _skill_warning(configured_id, "skill file must be a TOML table")

    for field in FORBIDDEN_SKILL_FIELDS:
        if field in payload:
            return None, _skill_warning(
                configured_id, f"skill file contains forbidden field: {field}"
            )

    skill_id = payload.get("id")
    if not isinstance(skill_id, str) or not skill_id:
        skill_id = configured_id
    if skill_id != configured_id:
        return None, _skill_warning(
            configured_id,
            f"skill id mismatch: config references {configured_id} but file declares {skill_id}",
        )

    name = payload.get("name")
    if not isinstance(name, str) or not name:
        return None, _skill_warning(configured_id, "skill file must include a non-empty name")

    deterministic_rules = _parse_deterministic_rules(
        payload.get("deterministic_rules"), configured_id
    )
    agent_reviews = _parse_agent_reviews(payload.get("agent_reviews"), configured_id)

    return {
        "id": configured_id,
        "name": name,
        "version": payload.get("version") if isinstance(payload.get("version"), str) else "0.1.0",
        "description": payload.get("description")
        if isinstance(payload.get("description"), str)
        else "",
        "path": path,
        "deterministic_rules": deterministic_rules,
        "agent_reviews": agent_reviews,
    }, None


def _parse_deterministic_rules(value: object, skill_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    rules: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rule_id = item.get("id")
        rule_type = item.get("type")
        paths = _string_list(item.get("paths"))
        message = item.get("message")
        risk = item.get("risk")
        expected = item.get("expected")
        if (
            not isinstance(rule_id, str)
            or not rule_id
            or not isinstance(rule_type, str)
            or not rule_type
            or not paths
            or not isinstance(message, str)
            or not message
            or not isinstance(risk, str)
            or not risk
            or not isinstance(expected, str)
            or not expected
        ):
            continue

        rule: dict[str, Any] = {
            "id": rule_id,
            "type": rule_type,
            "paths": paths,
            "message": message,
            "risk": risk,
            "expected": expected,
            "verification": item.get("verification")
            if isinstance(item.get("verification"), str)
            else f"Rerun quality-runner and confirm skill:{skill_id}/{rule_id} clears.",
        }
        category = item.get("category")
        if isinstance(category, str) and category:
            rule["category"] = category
        severity = item.get("severity")
        if severity in {"warning", "observation"}:
            rule["severity"] = severity

        if rule_type == "disallowed_pattern":
            patterns = _string_list(item.get("disallowed_patterns"))
            if patterns:
                rule["disallowed_patterns"] = patterns
                rules.append(rule)
        elif rule_type == "trigger_without_required":
            triggers = _string_list(item.get("trigger_patterns"))
            required = _string_list(item.get("required_patterns"))
            if triggers and required:
                rule["trigger_patterns"] = triggers
                rule["required_patterns"] = required
                rules.append(rule)
        elif rule_type == "import_boundary":
            disallowed = _string_list(item.get("disallowed_imports"))
            if disallowed:
                rule["disallowed_imports"] = disallowed
                rule["allowed_imports"] = _string_list(item.get("allowed_imports"))
                rules.append(rule)
    return rules


def _parse_agent_reviews(value: object, skill_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    reviews: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        review_id = item.get("id")
        paths = _string_list(item.get("paths"))
        rubric = item.get("rubric")
        if (
            not isinstance(review_id, str)
            or not review_id
            or not paths
            or not isinstance(rubric, str)
            or not rubric
        ):
            continue
        review: dict[str, Any] = {
            "id": review_id,
            "paths": paths,
            "rubric": rubric.strip(),
        }
        category = item.get("category")
        if isinstance(category, str) and category:
            review["category"] = category
        severity = item.get("severity")
        if severity in {"warning", "observation"}:
            review["severity"] = severity
        focus = _string_list(item.get("focus"))
        if focus:
            review["focus"] = focus
        reviews.append(review)
    return reviews


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _skill_warning(skill_id: str, message: str) -> dict[str, str]:
    return {
        "code": "invalid_quality_skill",
        "message": f"skill {skill_id}: {message}",
        "path": f".quality-runner/skills/{skill_id}.toml",
    }


def sanitize_skill_id(skill_id: str) -> str | None:
    normalized = skill_id.strip().lower().replace("_", "-")
    if not normalized or not SKILL_ID_RE.match(normalized):
        return None
    if ".." in normalized or "/" in normalized or "\\" in normalized:
        return None
    return normalized
