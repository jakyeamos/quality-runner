from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from quality_runner.schema_constants import GLOBAL_SKILL_CONFIG_SCHEMA, SKILL_SELECTION_SCHEMA
from quality_runner.skill_config import load_active_skills, sanitize_skill_id

GLOBAL_SKILL_CONFIG_ENV = "QUALITY_RUNNER_GLOBAL_CONFIG"
GLOBAL_SKILL_CORPUS_ENV = "QUALITY_RUNNER_SKILL_CORPUS"
DEFAULT_MIN_SCORE = 0.15
DEFAULT_MAX_ACTIVE = 12
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SELECTION_STOP_WORDS = frozenset(
    {
        "and",
        "are",
        "code",
        "file",
        "files",
        "for",
        "from",
        "into",
        "only",
        "pack",
        "packs",
        "path",
        "paths",
        "quality",
        "repo",
        "repository",
        "review",
        "reviews",
        "runner",
        "should",
        "source",
        "the",
        "this",
        "that",
        "with",
    }
)
_EXTENSION_SIGNALS = {
    "astro": "web",
    "css": "web",
    "html": "web",
    "jsx": "javascript",
    "js": "javascript",
    "json": "configuration",
    "less": "web",
    "md": "documentation",
    "mdx": "web",
    "py": "python",
    "rs": "rust",
    "sass": "web",
    "scss": "web",
    "sql": "database",
    "svelte": "web",
    "toml": "configuration",
    "ts": "typescript",
    "tsx": "typescript",
    "vue": "web",
    "yaml": "configuration",
    "yml": "configuration",
}
_MARKER_SIGNALS: dict[str, set[str]] = {
    "cargo.toml": {"rust"},
    "dockerfile": {"container", "deployment"},
    "go.mod": {"go"},
    "next.config.js": {"next", "react", "web"},
    "next.config.mjs": {"next", "react", "web"},
    "next.config.ts": {"next", "react", "web"},
    "package.json": {"javascript", "node", "web"},
    "prisma": {"database", "migration"},
    "pyproject.toml": {"python"},
    "pytest.ini": {"python", "tests"},
    "vite.config.js": {"javascript", "vite", "web"},
    "vite.config.ts": {"typescript", "vite", "web"},
}


def load_selected_skills(
    repo_root: Path,
    config: dict[str, Any],
    *,
    repo_signals: Iterable[str] | None = None,
    global_config_path: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    root = repo_root.expanduser().resolve()
    local_skills, local_warnings = load_active_skills(root, config)
    local_ids = [str(skill["id"]) for skill in local_skills if isinstance(skill.get("id"), str)]
    selection = _selection_base(local_ids=local_ids)
    selection["warnings"] = list(local_warnings)

    repo_skills = config.get("skills")
    if isinstance(repo_skills, dict) and repo_skills.get("enabled") is False:
        selection["status"] = "disabled"
        selection["source"] = "repository"
        return [], local_warnings, selection
    if isinstance(repo_skills, dict) and repo_skills.get("global_enabled") is False:
        selection["status"] = "disabled"
        selection["source"] = "repository"
        return local_skills, local_warnings, selection

    global_config, global_warnings = load_global_skill_config(global_config_path)
    selection["warnings"] = [*local_warnings, *global_warnings]
    if global_config is None:
        selection["status"] = "local-only" if local_skills else "not_configured"
        selection["source"] = "local" if local_skills else "none"
        return local_skills, [*local_warnings, *global_warnings], selection
    selection.update(
        {
            "global_config_path": global_config.get("path"),
            "corpus_path": (
                str(global_config["corpus_path"])
                if isinstance(global_config.get("corpus_path"), Path)
                else None
            ),
            "mode": global_config.get("mode", "relevant"),
            "min_score": global_config.get("min_score", DEFAULT_MIN_SCORE),
            "max_active": global_config.get("max_active", DEFAULT_MAX_ACTIVE),
        }
    )
    if global_config.get("enabled") is not True:
        selection["status"] = "disabled"
        selection["source"] = "local" if local_skills else "none"
        return local_skills, [*local_warnings, *global_warnings], selection

    corpus_path = global_config.get("corpus_path")
    if not isinstance(corpus_path, Path):
        warning = _global_warning(
            global_config.get("path"), "global skill config must include a corpus path"
        )
        selection["warnings"].append(warning)
        selection["status"] = "unavailable"
        selection["source"] = "local" if local_skills else "none"
        return local_skills, list(selection["warnings"]), selection

    from quality_runner.skill_corpus import load_skill_corpus

    corpus, corpus_errors = load_skill_corpus(corpus_path)
    if corpus is None:
        corpus_warnings = [
            _global_warning(global_config.get("path"), error) for error in corpus_errors
        ]
        selection["warnings"].extend(corpus_warnings)
        selection["status"] = "unavailable"
        selection["source"] = "local" if local_skills else "none"
        return local_skills, list(selection["warnings"]), selection

    signals = {
        token
        for value in (repo_signals or repository_skill_signals(root, []))
        for token in _tokens(str(value))
    }
    global_section = global_config
    global_excluded = _configured_ids(global_section, "exclude")
    repo_excluded = _configured_ids(repo_skills, "global_exclude")
    excluded = set(global_excluded) | set(repo_excluded)
    always = set(_configured_ids(global_section, "always")) | set(
        _configured_ids(repo_skills, "global_always")
    )
    configured_active = _configured_ids(global_section, "active")
    corpus_active = _configured_ids(corpus, "active")
    eligible_ids = (
        set(configured_active or corpus_active)
        if (configured_active or corpus_active)
        else {str(item["id"]) for item in corpus["packs"] if isinstance(item, dict)}
    )
    selection.update(
        {
            "status": "enabled",
            "source": "local+global" if local_skills else "global",
            "corpus_id": corpus.get("id"),
            "corpus_version": corpus.get("version"),
            "eligible_global_skill_ids": sorted(eligible_ids),
            "repo_signals": _diagnostic_signals(signals),
        }
    )

    candidates: list[dict[str, Any]] = []
    selected_entries: list[tuple[dict[str, Any], dict[str, Any]]] = []
    diagnostic_matches: set[str] = set()
    for pack_entry in corpus["packs"]:
        pack_id = str(pack_entry["id"])
        score, matched_terms = _pack_score(pack_entry, signals)
        diagnostic_matches.update(matched_terms)
        candidate: dict[str, Any] = {
            "id": pack_id,
            "score": score,
            "matched_terms": matched_terms,
        }
        if pack_id not in eligible_ids:
            candidate.update({"status": "not-eligible", "reason": "not in corpus active set"})
        elif pack_id in excluded:
            candidate.update({"status": "excluded", "reason": "excluded by configuration"})
        elif pack_id in local_ids:
            candidate.update({"status": "local-override", "reason": "local pack takes precedence"})
        elif pack_id in always:
            candidate.update({"status": "selected", "reason": "explicitly pinned"})
            selected_entries.append((pack_entry, candidate))
        elif global_config["mode"] == "all":
            candidate.update({"status": "selected", "reason": "global selection mode is all"})
            selected_entries.append((pack_entry, candidate))
        elif score >= float(global_config["min_score"]):
            candidate.update({"status": "selected", "reason": "repository signals are relevant"})
            selected_entries.append((pack_entry, candidate))
        else:
            candidate.update(
                {"status": "not-relevant", "reason": "score below relevance threshold"}
            )
        candidates.append(candidate)

    selection["repo_signals"] = _diagnostic_signals(signals, priority=diagnostic_matches)
    selected_entries.sort(
        key=lambda item: (
            0 if item[0]["id"] in always else 1,
            -float(item[1]["score"]),
            str(item[0]["id"]),
        )
    )
    selected_entries = selected_entries[: int(global_config["max_active"])]
    selected_ids = {str(entry["id"]) for entry, _candidate in selected_entries}
    for candidate in candidates:
        if candidate["status"] == "selected" and candidate["id"] not in selected_ids:
            candidate["status"] = "limited"
            candidate["reason"] = "max_active limit reached"

    selected_global_skills = [entry["pack"] for entry, _candidate in selected_entries]
    selection["candidates"] = sorted(candidates, key=lambda item: str(item["id"]))
    selection["selected_global_skill_ids"] = [str(entry["id"]) for entry, _ in selected_entries]
    selection["selected_skill_ids"] = [*local_ids, *selection["selected_global_skill_ids"]]
    return (
        [*local_skills, *selected_global_skills],
        list(selection["warnings"]),
        selection,
    )


def load_global_skill_config(
    global_config_path: Path | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    path = _discover_global_config_path(global_config_path)
    corpus_env = os.environ.get(GLOBAL_SKILL_CORPUS_ENV)
    if path is None and corpus_env:
        return (
            {
                "path": None,
                "corpus_path": Path(corpus_env).expanduser().resolve(),
                "enabled": True,
                "mode": "relevant",
                "min_score": DEFAULT_MIN_SCORE,
                "max_active": DEFAULT_MAX_ACTIVE,
                "active": [],
                "always": [],
                "exclude": [],
            },
            [],
        )
    if path is None:
        return None, []
    if not path.exists():
        return None, [_global_warning(path, "global skill config was not found")]

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        return None, [_global_warning(path, f"global skill config could not be parsed: {error}")]
    if not isinstance(raw, dict) or raw.get("schema") != GLOBAL_SKILL_CONFIG_SCHEMA:
        return None, [_global_warning(path, f"config schema must be {GLOBAL_SKILL_CONFIG_SCHEMA}")]
    quality_runner = raw.get("quality_runner")
    skills_section = quality_runner.get("skills") if isinstance(quality_runner, dict) else None
    if not isinstance(skills_section, dict):
        return None, [_global_warning(path, "config must include [quality_runner.skills]")]

    warnings: list[dict[str, str]] = []
    enabled = skills_section.get("enabled", True)
    if not isinstance(enabled, bool):
        warnings.append(_global_warning(path, "quality_runner.skills.enabled must be a boolean"))
        enabled = False
    corpus_value = skills_section.get("corpus")
    corpus_path: Path | None = None
    if isinstance(corpus_value, str) and corpus_value:
        corpus_path = Path(corpus_value).expanduser()
        if not corpus_path.is_absolute():
            corpus_path = path.parent / corpus_path
        corpus_path = corpus_path.resolve()
    else:
        warnings.append(_global_warning(path, "quality_runner.skills.corpus must be a path"))

    mode = skills_section.get("mode", "relevant")
    if mode not in {"relevant", "all"}:
        warnings.append(_global_warning(path, "quality_runner.skills.mode must be relevant or all"))
        mode = "relevant"
    min_score = skills_section.get("min_score", DEFAULT_MIN_SCORE)
    if (
        isinstance(min_score, bool)
        or not isinstance(min_score, (int, float))
        or not 0 <= min_score <= 1
    ):
        warnings.append(
            _global_warning(path, "quality_runner.skills.min_score must be between 0 and 1")
        )
        min_score = DEFAULT_MIN_SCORE
    max_active = skills_section.get("max_active", DEFAULT_MAX_ACTIVE)
    if not isinstance(max_active, int) or isinstance(max_active, bool) or not 1 <= max_active <= 50:
        warnings.append(
            _global_warning(path, "quality_runner.skills.max_active must be between 1 and 50")
        )
        max_active = DEFAULT_MAX_ACTIVE
    active = _config_ids(skills_section.get("active"), path, "active", warnings)
    always = _config_ids(skills_section.get("always"), path, "always", warnings)
    exclude = _config_ids(skills_section.get("exclude"), path, "exclude", warnings)
    return (
        {
            "path": str(path),
            "corpus_path": corpus_path,
            "enabled": enabled,
            "mode": mode,
            "min_score": float(min_score),
            "max_active": max_active,
            "active": active,
            "always": always,
            "exclude": exclude,
        },
        warnings,
    )


def repository_skill_signals(
    repo_root: Path,
    scanned_files: Iterable[dict[str, Any]],
) -> list[str]:
    root = repo_root.expanduser().resolve()
    values: list[str] = []
    for item in scanned_files:
        path = item.get("path") if isinstance(item, dict) else None
        if not isinstance(path, str):
            continue
        values.append(path)
        suffix = Path(path).suffix.lower().lstrip(".")
        if suffix in _EXTENSION_SIGNALS:
            values.append(_EXTENSION_SIGNALS[suffix])
    try:
        entries = list(root.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        name = entry.name.lower()
        values.append(name)
        values.extend(_MARKER_SIGNALS.get(name, set()))
        if name in {".github", ".gitlab", "migrations", "prisma", "tests", "e2e"}:
            values.append(name.lstrip("."))
    return sorted({token for value in values for token in _tokens(value)})


def _selection_base(*, local_ids: list[str]) -> dict[str, Any]:
    return {
        "schema": SKILL_SELECTION_SCHEMA,
        "status": "not_configured",
        "source": "none",
        "global_config_path": None,
        "corpus_path": None,
        "corpus_id": None,
        "corpus_version": None,
        "mode": "relevant",
        "min_score": DEFAULT_MIN_SCORE,
        "max_active": DEFAULT_MAX_ACTIVE,
        "eligible_global_skill_ids": [],
        "selected_local_skill_ids": local_ids,
        "selected_global_skill_ids": [],
        "selected_skill_ids": list(local_ids),
        "repo_signals": [],
        "candidates": [],
        "warnings": [],
    }


def _discover_global_config_path(requested_path: Path | None) -> Path | None:
    if requested_path is not None:
        path = requested_path.expanduser().resolve()
        return path / "quality-runner.toml" if path.is_dir() else path
    environment_path = os.environ.get(GLOBAL_SKILL_CONFIG_ENV)
    if environment_path:
        path = Path(environment_path).expanduser().resolve()
        return path / "quality-runner.toml" if path.is_dir() else path
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    candidates = [
        config_home / "quality-runner" / "quality-runner.toml",
        Path("~/.quality-runner/quality-runner.toml").expanduser(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _configured_ids(section: object, key: str) -> list[str]:
    if not isinstance(section, dict):
        return []
    value = section.get(key)
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        skill_id = sanitize_skill_id(item) if isinstance(item, str) else None
        if skill_id is not None and skill_id not in normalized:
            normalized.append(skill_id)
    return normalized


def _config_ids(
    value: object,
    path: Path,
    key: str,
    warnings: list[dict[str, str]],
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(_global_warning(path, f"quality_runner.skills.{key} must be a list"))
        return []
    normalized: list[str] = []
    for item in value:
        skill_id = sanitize_skill_id(item) if isinstance(item, str) else None
        if skill_id is None:
            warnings.append(
                _global_warning(path, f"quality_runner.skills.{key} contains an invalid id")
            )
            continue
        if skill_id not in normalized:
            normalized.append(skill_id)
    return normalized


def _pack_score(pack_entry: dict[str, Any], signals: set[str]) -> tuple[float, list[str]]:
    pack = pack_entry.get("pack")
    if not isinstance(pack, dict):
        return 0.0, []
    focus = _tokens(" ".join(str(item) for item in pack_entry.get("focus", [])))
    terms = _pack_terms(pack)
    selection_terms = focus or terms
    match_terms = sorted(signals & selection_terms)
    denominator = max(1, min(len(selection_terms), 8))
    score = round(min(1.0, len(match_terms) / denominator), 3)
    return score, match_terms


def _pack_terms(pack: dict[str, Any]) -> set[str]:
    values: list[str] = []
    for key in ("id", "name", "description"):
        value = pack.get(key)
        if isinstance(value, str):
            values.append(value)
    for collection_key in ("deterministic_rules", "agent_reviews"):
        collection = pack.get(collection_key)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            for value in item.values():
                if isinstance(value, str):
                    values.append(value)
                elif isinstance(value, list):
                    values.extend(
                        str(item_value) for item_value in value if isinstance(item_value, str)
                    )
    return {token for value in values for token in _tokens(value)}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(value.lower().replace("_", " ").replace("-", " "))
        if token not in _SELECTION_STOP_WORDS
    }


def _diagnostic_signals(signals: set[str], *, priority: set[str] | None = None) -> list[str]:
    meaningful = {token for token in signals if not token.isdigit()}
    prioritized = sorted(meaningful & (priority or set()))
    remainder = sorted(meaningful - set(prioritized))
    return [*prioritized, *remainder][:160]


def _global_warning(path: object, message: str) -> dict[str, str]:
    return {
        "code": "invalid_quality_runner_global_skill_config",
        "message": f"global Quality Skill config: {message}",
        "path": str(path) if path else "<global-quality-runner-config>",
    }
