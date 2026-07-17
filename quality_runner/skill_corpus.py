from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

from quality_runner.schema_constants import (
    SKILL_APPEND_RESULT_SCHEMA,
    SKILL_CLASSIFICATION_SCHEMA,
    SKILL_SYNC_RESULT_SCHEMA,
)
from quality_runner.skill_config import _load_skill_pack, _resolve_skill_path, sanitize_skill_id
from quality_runner.skill_ingest import append_skill_to_target, validate_skill_pack
from quality_runner.skill_registration import _canonical_skill_toml, update_repo_skills_config

CORPUS_SCHEMA = "quality-runner-skill-corpus-v0.1"
CORPUS_MANIFEST_NAME = "quality-runner-corpus.toml"
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_STOP_WORDS = frozenset(
    {
        "and",
        "for",
        "from",
        "into",
        "must",
        "only",
        "should",
        "that",
        "the",
        "this",
        "with",
    }
)


def classify_skill_pack(
    candidate_path: Path,
    *,
    skill_id: str,
    corpus_path: Path,
) -> dict[str, Any]:
    corpus, corpus_errors = load_skill_corpus(corpus_path)
    if corpus is None:
        return {
            "schema": SKILL_CLASSIFICATION_SCHEMA,
            "status": "rejected",
            "candidate_skill_id": skill_id,
            "recommended_pack_id": None,
            "recommendations": [],
            "warnings": [],
            "errors": corpus_errors,
        }

    validation = validate_skill_pack(
        candidate_path,
        skill_id=skill_id,
        repo_root=candidate_path.expanduser().resolve().parent,
    )
    if validation.get("status") == "rejected":
        return {
            "schema": SKILL_CLASSIFICATION_SCHEMA,
            "status": "rejected",
            "candidate_skill_id": skill_id,
            "recommended_pack_id": None,
            "recommendations": [],
            "warnings": validation.get("warnings", []),
            "errors": validation.get("errors", []),
        }

    candidate_pack, candidate_warning = _load_skill_pack(
        candidate_path.expanduser().resolve(), str(validation["skill_id"])
    )
    warnings = list(validation.get("warnings", []))
    if candidate_warning is not None:
        warnings.append(candidate_warning["message"])
    if candidate_pack is None:
        return {
            "schema": SKILL_CLASSIFICATION_SCHEMA,
            "status": "rejected",
            "candidate_skill_id": skill_id,
            "recommended_pack_id": None,
            "recommendations": [],
            "warnings": warnings,
            "errors": ["candidate pack failed validation"],
        }

    candidate_terms = _pack_terms(candidate_pack)
    recommendations: list[dict[str, Any]] = []
    for pack_entry in corpus["packs"]:
        pack = pack_entry["pack"]
        terms = _pack_terms(pack, extra=pack_entry["focus"])
        overlap = sorted(candidate_terms & terms)
        denominator = max(1, min(len(candidate_terms), len(terms)))
        score = round(min(1.0, len(overlap) / denominator), 3)
        if len(overlap) >= 2 and score >= 0.15:
            fit = "likely"
        elif overlap:
            fit = "possible"
        else:
            fit = "no-fit"
        recommendations.append(
            {
                "pack_id": pack_entry["id"],
                "fit": fit,
                "score": score,
                "overlap": overlap,
                "reason": (
                    f"shared terms: {', '.join(overlap)}"
                    if overlap
                    else "no shared classification terms"
                ),
            }
        )

    recommendations.sort(key=lambda item: (-float(item["score"]), str(item["pack_id"])))
    recommended = next(
        (item["pack_id"] for item in recommendations if item["fit"] != "no-fit"),
        None,
    )
    return {
        "schema": SKILL_CLASSIFICATION_SCHEMA,
        "status": "classified",
        "candidate_skill_id": str(validation["skill_id"]),
        "recommended_pack_id": recommended,
        "recommendations": recommendations,
        "warnings": warnings,
        "errors": [],
    }


def append_skill_to_corpus(
    candidate_path: Path,
    *,
    source_skill_id: str,
    pack_id: str,
    corpus_path: Path,
    source_ref: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    corpus, errors = load_skill_corpus(corpus_path)
    if corpus is None:
        return {
            "schema": SKILL_APPEND_RESULT_SCHEMA,
            "status": "rejected",
            "write": False,
            "source_skill_id": source_skill_id,
            "pack_id": pack_id,
            "corpus_path": str(corpus_path.expanduser().resolve()),
            "warnings": [],
            "errors": errors,
        }

    normalized_pack_id = sanitize_skill_id(pack_id)
    if normalized_pack_id is None:
        return {
            "schema": SKILL_APPEND_RESULT_SCHEMA,
            "status": "rejected",
            "write": False,
            "source_skill_id": source_skill_id,
            "pack_id": pack_id,
            "corpus_path": str(corpus["path"]),
            "warnings": [],
            "errors": ["pack id must be a valid skill id"],
        }
    pack_entry = next(
        (entry for entry in corpus["packs"] if entry["id"] == normalized_pack_id),
        None,
    )
    if pack_entry is None:
        return {
            "schema": SKILL_APPEND_RESULT_SCHEMA,
            "status": "rejected",
            "write": False,
            "source_skill_id": source_skill_id,
            "pack_id": pack_id,
            "corpus_path": str(corpus["path"]),
            "warnings": [],
            "errors": [f"corpus pack not found: {pack_id}"],
        }

    result = append_skill_to_target(
        candidate_path,
        source_skill_id=source_skill_id,
        pack_id=normalized_pack_id,
        target_path=pack_entry["path"],
        source_ref=source_ref,
        write=write,
    )
    result["corpus_path"] = str(corpus["path"])
    result["target_path"] = str(pack_entry["path"])
    return result


def load_skill_corpus(corpus_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    manifest_path = corpus_path.expanduser().resolve()
    if manifest_path.is_dir():
        manifest_path = manifest_path / CORPUS_MANIFEST_NAME
    if not manifest_path.exists():
        return None, [f"corpus manifest not found: {manifest_path}"]

    try:
        raw = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        return None, [f"corpus manifest could not be parsed: {error}"]
    if not isinstance(raw, dict):
        return None, ["corpus manifest must be a TOML table"]
    if raw.get("schema") != CORPUS_SCHEMA:
        return None, [f"corpus manifest schema must be {CORPUS_SCHEMA}"]

    corpus_id = raw.get("id")
    if not isinstance(corpus_id, str) or not corpus_id:
        return None, ["corpus manifest must include a non-empty id"]
    version = raw.get("version", "0.1.0")
    if not isinstance(version, str) or not version:
        return None, ["corpus manifest version must be a non-empty string"]

    pack_entries = raw.get("packs")
    if not isinstance(pack_entries, list) or not pack_entries:
        return None, ["corpus manifest must include at least one [[packs]] entry"]

    corpus_root = manifest_path.parent
    packs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    errors: list[str] = []
    for index, item in enumerate(pack_entries):
        if not isinstance(item, dict):
            errors.append(f"packs[{index}] must be a table")
            continue
        pack_id = item.get("id")
        normalized_id = sanitize_skill_id(pack_id) if isinstance(pack_id, str) else None
        if normalized_id is None:
            errors.append(f"packs[{index}] must include a valid id")
            continue
        if normalized_id in seen_ids:
            errors.append(f"packs[{index}] duplicates id {normalized_id}")
            continue
        seen_ids.add(normalized_id)
        relative_path = item.get("path")
        if not isinstance(relative_path, str) or not relative_path:
            errors.append(f"packs[{index}] must include a path")
            continue
        pack_path, path_warning = _resolve_skill_path(corpus_root, relative_path)
        if pack_path is None or path_warning is not None:
            errors.append(f"packs[{index}] path rejected for traversal safety: {relative_path}")
            continue
        pack, warning = _load_skill_pack(pack_path, normalized_id)
        if warning is not None:
            errors.append(warning["message"])
        if pack is None:
            errors.append(f"packs[{index}] failed validation: {relative_path}")
            continue
        focus = item.get("focus")
        focus_terms = (
            [value for value in focus if isinstance(value, str) and value]
            if isinstance(focus, list)
            else []
        )
        packs.append(
            {
                "id": normalized_id,
                "path": pack_path,
                "focus": focus_terms,
                "pack": pack,
            }
        )

    active = raw.get("active")
    if active is not None and not isinstance(active, list):
        errors.append("corpus active must be a list of pack ids")
        active_ids: list[str] = []
    else:
        active_ids = []
        for value in active or []:
            normalized_active = sanitize_skill_id(value) if isinstance(value, str) else None
            if normalized_active is None:
                errors.append(f"corpus active contains invalid pack id: {value}")
            else:
                active_ids.append(normalized_active)
    active_ids = list(dict.fromkeys(active_ids))
    unknown_active = sorted(set(active_ids) - seen_ids)
    if unknown_active:
        errors.append(f"corpus active list references unknown packs: {', '.join(unknown_active)}")
    if errors:
        return None, errors
    return {
        "id": corpus_id,
        "version": version,
        "path": manifest_path,
        "active": active_ids,
        "packs": packs,
    }, []


def sync_skill_corpus(
    corpus_path: Path,
    *,
    repo_roots: list[Path],
    write: bool = False,
    replace_active: bool = False,
) -> dict[str, Any]:
    corpus, errors = load_skill_corpus(corpus_path)
    if corpus is None:
        return {
            "schema": SKILL_SYNC_RESULT_SCHEMA,
            "status": "rejected",
            "write": False,
            "corpus_path": str(corpus_path.expanduser().resolve()),
            "repositories": [],
            "warnings": [],
            "errors": errors,
        }

    plans: list[dict[str, Any]] = []
    for repo_path in repo_roots:
        repo_root = repo_path.expanduser().resolve()
        repo_errors: list[str] = []
        pack_plans: list[dict[str, Any]] = []
        if not repo_root.is_dir():
            repo_errors.append(f"repository path is not a directory: {repo_root}")
        for pack_entry in corpus["packs"]:
            skill_id = pack_entry["id"]
            target_path, target_warning = _resolve_skill_path(
                repo_root, f".quality-runner/skills/{skill_id}.toml"
            )
            if target_path is None or target_warning is not None:
                repo_errors.append(f"target path rejected for {skill_id}")
                continue
            canonical_content = _canonical_skill_toml(pack_entry["pack"], skill_id)
            pack_plans.append(
                {
                    "id": skill_id,
                    "source_path": str(pack_entry["path"]),
                    "target_path": str(target_path),
                    "target_relative_path": f".quality-runner/skills/{skill_id}.toml",
                    "changed": not target_path.exists()
                    or target_path.read_text(encoding="utf-8") != canonical_content,
                    "canonical_content": canonical_content,
                }
            )
        plans.append(
            {
                "repo_path": str(repo_root),
                "config_path": str(repo_root / ".quality-runner.toml"),
                "packs": pack_plans,
                "active": list(corpus["active"]),
                "errors": repo_errors,
            }
        )

    all_errors = [error for plan in plans for error in plan["errors"]]
    if all_errors:
        return {
            "schema": SKILL_SYNC_RESULT_SCHEMA,
            "status": "rejected",
            "write": False,
            "corpus_path": str(corpus["path"]),
            "repositories": _public_plans(plans),
            "warnings": [],
            "errors": all_errors,
        }

    if write:
        for plan in plans:
            repo_root = Path(plan["repo_path"])
            for pack_plan in plan["packs"]:
                target_path = Path(pack_plan["target_path"])
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if pack_plan["changed"]:
                    target_path.write_text(pack_plan["canonical_content"], encoding="utf-8")
            update_repo_skills_config(
                repo_root,
                entries=[
                    {"id": pack_plan["id"], "path": pack_plan["target_relative_path"]}
                    for pack_plan in plan["packs"]
                ],
                activate_ids=plan["active"],
                replace_active=replace_active,
            )

    return {
        "schema": SKILL_SYNC_RESULT_SCHEMA,
        "status": "synchronized" if write else "planned",
        "write": write,
        "corpus_path": str(corpus["path"]),
        "repositories": _public_plans(plans),
        "warnings": [],
        "errors": [],
    }


def _pack_terms(pack: dict[str, Any], *, extra: list[str] | None = None) -> set[str]:
    values: list[str] = []
    for key in ("id", "name", "description"):
        value = pack.get(key)
        if isinstance(value, str):
            values.append(value)
    if extra:
        values.extend(extra)
    for collection_key in ("deterministic_rules", "agent_reviews"):
        collection = pack.get(collection_key)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            values.extend(str(value) for value in item.values() if isinstance(value, str))
            for value in item.values():
                if isinstance(value, list):
                    values.extend(
                        str(item_value) for item_value in value if isinstance(item_value, str)
                    )
    return {
        token
        for value in values
        for token in _TOKEN_RE.findall(value.lower())
        if token not in _STOP_WORDS
    }


def _public_plans(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "repo_path": plan["repo_path"],
            "config_path": plan["config_path"],
            "active": plan["active"],
            "errors": plan["errors"],
            "packs": [
                {
                    "id": pack_plan["id"],
                    "source_path": pack_plan["source_path"],
                    "target_path": pack_plan["target_path"],
                    "changed": pack_plan["changed"],
                }
                for pack_plan in plan["packs"]
            ],
        }
        for plan in plans
    ]
