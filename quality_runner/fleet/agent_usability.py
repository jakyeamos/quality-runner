from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from quality_runner.fleet.contracts import FRESHNESS_DAYS, MAX_DOCUMENT_BYTES, relative_path

AGENT_USABILITY_SCHEMA = "quality-runner-agent-usability/v1"
AGENT_USABILITY_MANIFEST_SCHEMA = "agent-usability/v1"
AGENT_USABILITY_MANIFEST_PATH = Path(".agents/agent-usability.json")
MAX_INVENTORY_ITEMS = 500
MAX_SKILL_FAMILY_SIZE = 12


def assess_agent_usability(
    root: Path,
    documents: dict[str, str],
    link_evidence: dict[str, Any],
    as_of: str,
) -> dict[str, Any]:
    manifest, manifest_error = _read_manifest(root)
    declared_applicability = manifest.get("applicability", "applicable")
    if manifest and declared_applicability not in {"applicable", "not_applicable"}:
        manifest_error = "Agent-usability applicability must be applicable or not_applicable."
    if manifest and declared_applicability == "not_applicable":
        if not isinstance(manifest.get("reason"), str) or not manifest["reason"].strip():
            manifest_error = "A not_applicable agent-usability manifest requires a reason."
        elif _objects(manifest.get("tools")) or _objects(manifest.get("skills")):
            manifest_error = "A not_applicable manifest cannot declare tools or skills."
    explicit_not_applicable = (
        bool(manifest) and declared_applicability == "not_applicable" and manifest_error is None
    )
    document_paths, document_inventory_truncated = _document_inventory(root)
    hosted_skill_paths, skill_inventory_truncated = _skill_inventory(root)
    tools = _objects(manifest.get("tools"))
    declared_skills = _objects(manifest.get("skills"))
    declared_skill_ids = {
        str(item.get("id"))
        for item in declared_skills
        if isinstance(item.get("id"), str) and item.get("id")
    }
    valid_declared_skill_ids: set[str] = set()
    invalid_skill_contract_ids: set[str] = set()
    for item in declared_skills:
        identifier = item.get("id")
        source = item.get("source")
        contract_path = item.get("contract_path")
        if not isinstance(identifier, str) or not identifier:
            continue
        if source == "projected" or (
            source == "hosted"
            and isinstance(contract_path, str)
            and _local_file(root, contract_path)
        ):
            valid_declared_skill_ids.add(identifier)
        else:
            invalid_skill_contract_ids.add(identifier)
    hosted_skill_ids = {path.parent.name for path in hosted_skill_paths}
    known_skill_ids = valid_declared_skill_ids | hosted_skill_ids
    all_skill_ids = declared_skill_ids | hosted_skill_ids

    agent_document_paths = {
        path
        for path in document_paths
        if path in {"AGENTS.md", "CLAUDE.md"} or path.startswith((".agents/context/", ".context/"))
    }
    mapped_document_paths: set[str] = set()
    missing_document_paths: set[str] = set()
    missing_skill_ids: set[str] = set()
    missing_evidence_paths: set[str] = set()
    documented_tool_count = 0
    skill_covered_tool_count = 0
    behavior_declared_tool_count = 0
    behavior_verified_tool_count = 0

    for tool in tools:
        docs = _strings(tool.get("documentation"))
        skills = _strings(tool.get("skills"))
        evidence = _evidence_items(tool.get("behavior_evidence"))
        mapped_document_paths.update(docs)
        existing_docs = [path for path in docs if _local_file(root, path)]
        missing_document_paths.update(path for path in docs if path not in existing_docs)
        existing_skills = [skill for skill in skills if skill in known_skill_ids]
        missing_skill_ids.update(skill for skill in skills if skill not in existing_skills)
        if docs and len(existing_docs) == len(docs):
            documented_tool_count += 1
        if skills and len(existing_skills) == len(skills):
            skill_covered_tool_count += 1
        existing_evidence = [
            item for item in evidence if _local_file(root, str(item.get("path", "")))
        ]
        missing_evidence_paths.update(
            str(item.get("path", ""))
            for item in evidence
            if item not in existing_evidence and item.get("path")
        )
        if existing_evidence:
            behavior_declared_tool_count += 1
        if any(_fresh_passed_evidence(item, as_of) for item in existing_evidence):
            behavior_verified_tool_count += 1

    agent_document_paths.update(mapped_document_paths)
    routed_agent_documents = _routed_agent_documents(agent_document_paths, link_evidence)
    reviewed_at = (
        manifest.get("reviewed_at") if isinstance(manifest.get("reviewed_at"), str) else None
    )
    manifest_fresh = _is_fresh_date(reviewed_at, as_of)
    manifest_present = bool(manifest)
    surface_present = bool(agent_document_paths or all_skill_ids or tools or manifest_error)

    lanes = [
        _documentation_lane(
            tool_count=len(tools),
            documented_tool_count=documented_tool_count,
            missing_paths=missing_document_paths,
            manifest_present=manifest_present,
            manifest_fresh=manifest_fresh,
            routed_count=len(routed_agent_documents),
            agent_document_count=len(agent_document_paths),
        ),
        _skill_coverage_lane(
            tool_count=len(tools),
            covered_tool_count=skill_covered_tool_count,
            missing_skill_ids=missing_skill_ids,
            manifest_present=manifest_present,
        ),
        _behavior_lane(
            tool_count=len(tools),
            declared_tool_count=behavior_declared_tool_count,
            verified_tool_count=behavior_verified_tool_count,
            missing_paths=missing_evidence_paths,
            manifest_present=manifest_present,
        ),
        _freshness_lane(
            manifest_present=manifest_present,
            manifest_error=manifest_error,
            manifest_fresh=manifest_fresh,
            reviewed_at=reviewed_at,
            missing_path_count=(
                len(missing_document_paths | missing_evidence_paths)
                + len(missing_skill_ids)
                + len(invalid_skill_contract_ids)
            ),
        ),
    ]
    if not surface_present or explicit_not_applicable:
        lanes = [
            {**lane, "applicable": False, "score": None, "status": "not_applicable"}
            for lane in lanes
        ]

    family_sizes: dict[str, int] = {}
    for item in declared_skills:
        family = item.get("family")
        if isinstance(family, str) and family:
            family_sizes[family] = family_sizes.get(family, 0) + 1
    classified_skill_ids = {
        str(item.get("id"))
        for item in declared_skills
        if isinstance(item.get("id"), str)
        and item.get("id")
        and isinstance(item.get("family"), str)
        and item.get("family")
    }
    oversized_document_count = sum(
        1 for path in document_paths if _file_size(root / path) > MAX_DOCUMENT_BYTES
    )
    oversized_skill_count = sum(
        1 for path in hosted_skill_paths if _file_size(path) > MAX_DOCUMENT_BYTES
    )
    unclassified_skill_count = len(all_skill_ids - classified_skill_ids)
    unrouted_agent_document_count = len(agent_document_paths - routed_agent_documents)
    growth_reasons: list[str] = []
    if document_inventory_truncated or skill_inventory_truncated:
        growth_reasons.append("bounded inventory limit reached")
    if unrouted_agent_document_count:
        growth_reasons.append(f"{unrouted_agent_document_count} agent document(s) are not routed")
    if unclassified_skill_count:
        growth_reasons.append(f"{unclassified_skill_count} skill(s) are not assigned to a family")
    if max(family_sizes.values(), default=0) > MAX_SKILL_FAMILY_SIZE:
        growth_reasons.append("a skill family exceeds the reviewable size threshold")
    if oversized_document_count or oversized_skill_count:
        growth_reasons.append("one or more documents exceed the bounded audit size")
    if (
        missing_document_paths
        or missing_skill_ids
        or missing_evidence_paths
        or invalid_skill_contract_ids
    ):
        growth_reasons.append("the manifest contains unresolved references")
    if not surface_present:
        growth_status = "not_applicable"
    elif document_inventory_truncated or skill_inventory_truncated or manifest_error:
        growth_status = "blocked"
    elif growth_reasons:
        growth_status = "attention"
    else:
        growth_status = "healthy"

    applicable_lanes = [lane for lane in lanes if lane["applicable"]]
    covered_lane_count = sum(
        1 for lane in applicable_lanes if isinstance(lane.get("score"), int) and lane["score"] >= 3
    )
    if not applicable_lanes:
        status = "not_applicable"
    elif any(lane["status"] == "blocked" for lane in applicable_lanes):
        status = "blocked"
    elif (
        covered_lane_count == len(applicable_lanes)
        and next(lane for lane in lanes if lane["id"] == "behavior_evidence")["score"] == 4
        and growth_status == "healthy"
    ):
        status = "healthy"
    else:
        status = "attention"

    return {
        "schema": AGENT_USABILITY_SCHEMA,
        "status": status,
        "applicability": "not_applicable" if explicit_not_applicable else "applicable",
        "manifest_status": "invalid"
        if manifest_error
        else "present"
        if manifest_present
        else "missing",
        "manifest_path": AGENT_USABILITY_MANIFEST_PATH.as_posix(),
        "applicable_lane_count": len(applicable_lanes),
        "covered_lane_count": covered_lane_count,
        "lanes": lanes,
        "growth_health": {
            "status": growth_status,
            "message": "; ".join(growth_reasons)
            if growth_reasons
            else "Documentation and skill structure remains proportionate and routed.",
            "document_count": len(document_paths),
            "agent_document_count": len(agent_document_paths),
            "routed_agent_document_count": len(routed_agent_documents),
            "unrouted_agent_document_count": unrouted_agent_document_count,
            "oversized_document_count": oversized_document_count,
            "skill_count": len(all_skill_ids),
            "family_count": len(family_sizes),
            "largest_family_size": max(family_sizes.values(), default=0),
            "unclassified_skill_count": unclassified_skill_count,
            "oversized_skill_count": oversized_skill_count,
            "tool_count": len(tools),
            "documented_tool_count": documented_tool_count,
            "skill_covered_tool_count": skill_covered_tool_count,
            "behavior_declared_tool_count": behavior_declared_tool_count,
            "behavior_verified_tool_count": behavior_verified_tool_count,
            "inventory_truncated": document_inventory_truncated or skill_inventory_truncated,
        },
    }


def _documentation_lane(**values: Any) -> dict[str, Any]:
    tool_count = cast(int, values["tool_count"])
    documented = cast(int, values["documented_tool_count"])
    missing = cast(set[str], values["missing_paths"])
    if not values["manifest_present"]:
        score, status = (2, "untracked") if values["agent_document_count"] else (0, "absent")
        message = "Agent documentation exists, but no repository-owned tool mapping was found."
    elif not tool_count or not documented:
        score, status, message = (
            1,
            "missing",
            "No agent-facing tool has a complete documentation mapping.",
        )
    elif documented < tool_count or missing:
        score, status, message = (
            2,
            "partial",
            "Some agent-facing tools have incomplete documentation references.",
        )
    elif values["manifest_fresh"] and values["routed_count"] == values["agent_document_count"]:
        score, status, message = (
            4,
            "maintained",
            "Every declared tool has fresh, routed documentation.",
        )
    else:
        score, status, message = (
            3,
            "validated",
            "Every declared tool has an existing documentation reference.",
        )
    return _lane("documentation_contract", "Documentation contract", score, status, message)


def _skill_coverage_lane(**values: Any) -> dict[str, Any]:
    tool_count = cast(int, values["tool_count"])
    covered = cast(int, values["covered_tool_count"])
    if not values["manifest_present"]:
        score, status, message = 0, "untracked", "Tool-to-skill coverage is not declared."
    elif not tool_count or not covered:
        score, status, message = 1, "missing", "No declared agent-facing tool is mapped to a skill."
    elif covered < tool_count or values["missing_skill_ids"]:
        score, status, message = 2, "partial", "Some tool-to-skill mappings are incomplete."
    else:
        score, status, message = (
            3,
            "static_validated",
            "Every declared tool maps to a known hosted or projected skill.",
        )
    return _lane("tool_skill_coverage", "Tool-to-skill coverage", score, status, message)


def _behavior_lane(**values: Any) -> dict[str, Any]:
    tool_count = cast(int, values["tool_count"])
    declared = cast(int, values["declared_tool_count"])
    verified = cast(int, values["verified_tool_count"])
    if not values["manifest_present"]:
        score, status, message = 0, "untracked", "Skill behavior evidence is not declared."
    elif not tool_count or not declared:
        score, status, message = (
            1,
            "missing",
            "No declared tool has repository-owned behavior evidence.",
        )
    elif values["missing_paths"] or declared < tool_count:
        score, status, message = (
            2,
            "partial",
            "Behavior evidence exists for only part of the declared tool surface.",
        )
    elif verified < tool_count:
        score, status, message = (
            3,
            "declared",
            "Behavior evidence is linked, but fresh passing receipts are incomplete.",
        )
    else:
        score, status, message = (
            4,
            "behavior_verified",
            "Every declared tool has fresh passing behavior evidence.",
        )
    return _lane("behavior_evidence", "Behavior evidence", score, status, message)


def _freshness_lane(**values: Any) -> dict[str, Any]:
    if values["manifest_error"]:
        score, status, message = 1, "blocked", cast(str, values["manifest_error"])
    elif not values["manifest_present"]:
        score, status, message = (
            0,
            "untracked",
            "No portability and freshness contract is declared.",
        )
    elif values["missing_path_count"]:
        score, status, message = (
            2,
            "static_gaps",
            "Portability is reduced by unresolved repository-relative references.",
        )
    elif not values["reviewed_at"]:
        score, status, message = 2, "unknown", "The agent-usability manifest has no review date."
    elif not values["manifest_fresh"]:
        score, status, message = (
            2,
            "stale",
            "The agent-usability manifest is outside the freshness window.",
        )
    else:
        score, status, message = (
            3,
            "static_validated",
            "Repository-relative references and manifest freshness passed static validation.",
        )
    return _lane("freshness_portability", "Freshness and portability", score, status, message)


def _lane(identifier: str, label: str, score: int, status: str, message: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": label,
        "applicable": True,
        "score": score,
        "status": status,
        "message": message,
    }


def _read_manifest(root: Path) -> tuple[dict[str, Any], str | None]:
    path = root / AGENT_USABILITY_MANIFEST_PATH
    if not path.is_file() or path.is_symlink():
        return {}, None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {}, f"Agent-usability manifest could not be parsed: {error}"
    if not isinstance(value, dict) or value.get("schema") != AGENT_USABILITY_MANIFEST_SCHEMA:
        return {}, f"Agent-usability manifest must use {AGENT_USABILITY_MANIFEST_SCHEMA}."
    return cast(dict[str, Any], value), None


def _document_inventory(root: Path) -> tuple[list[str], bool]:
    candidates = [
        root / name for name in ("AGENTS.md", "CLAUDE.md", "README.md", "CONTRIBUTING.md")
    ]
    for directory in (root / "docs", root / ".agents" / "context", root / ".context"):
        if directory.is_dir() and not directory.is_symlink():
            candidates.extend(sorted(directory.rglob("*.md")))
    paths = sorted(
        {
            relative_path(root, path)
            for path in candidates
            if path.is_file() and not path.is_symlink()
        }
    )
    return paths[:MAX_INVENTORY_ITEMS], len(paths) > MAX_INVENTORY_ITEMS


def _skill_inventory(root: Path) -> tuple[list[Path], bool]:
    paths: list[Path] = []
    for directory in (root / "skills", root / ".agents" / "skills", root / ".claude" / "skills"):
        if directory.is_dir() and not directory.is_symlink():
            paths.extend(sorted(directory.glob("*/SKILL.md")))
    unique = sorted({path for path in paths if path.is_file() and not path.is_symlink()})
    return unique[:MAX_INVENTORY_ITEMS], len(unique) > MAX_INVENTORY_ITEMS


def _routed_agent_documents(paths: set[str], link_evidence: dict[str, Any]) -> set[str]:
    routers = {".agents/context/README.md", ".context/README.md"} & paths
    routed = set(routers)
    for item in _objects(link_evidence.get("links")):
        if (
            item.get("source") in routers
            and item.get("status") == "valid"
            and item.get("target") in paths
        ):
            routed.add(str(item["target"]))
    return routed


def _evidence_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            items.append({"path": item})
        elif isinstance(item, dict) and isinstance(item.get("path"), str):
            items.append(cast(dict[str, Any], item))
    return items


def _fresh_passed_evidence(item: dict[str, Any], as_of: str) -> bool:
    return item.get("status") == "passed" and _is_fresh_date(item.get("observed_at"), as_of)


def _is_fresh_date(value: object, as_of: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        current = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current - observed <= timedelta(days=FRESHNESS_DAYS)


def _local_file(root: Path, value: str) -> bool:
    if not value or value.startswith(("/", "~")) or ".." in Path(value).parts:
        return False
    current = root
    for part in Path(value).parts:
        current /= part
        if current.is_symlink():
            return False
    try:
        return current.is_file() and current.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _strings(value: object) -> list[str]:
    return (
        [item for item in value if isinstance(item, str) and item]
        if isinstance(value, list)
        else []
    )


def _objects(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in value if isinstance(item, dict)]
