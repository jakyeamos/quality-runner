from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Literal, TypedDict, cast

from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text
from quality_runner.schema_constants import SKILL_DECOMPOSITION_SCHEMA

KnowledgeRole = Literal["format", "tool", "workflow", "adapter", "detector"]
Enforceability = Literal["deterministic", "agent_review", "context_only"]
NormalizationStatus = Literal[
    "not_applicable",
    "normalized",
    "partially_normalized",
    "unavailable",
]
MappingStatus = Literal["mapped", "context_only", "unmapped", "ambiguous"]

_KNOWLEDGE_ROLES = frozenset({"format", "tool", "workflow", "adapter", "detector"})
_ENFORCEABILITY = frozenset({"deterministic", "agent_review", "context_only"})
_MAPPING_STATUS = frozenset({"mapped", "context_only", "unmapped", "ambiguous"})
_NORMALIZATION_STATUS = frozenset(
    {"not_applicable", "normalized", "partially_normalized", "unavailable"}
)


class DecompositionUnit(TypedDict):
    id: str
    source: str
    revision: str
    path: str
    locator: str
    knowledge_role: KnowledgeRole
    enforceability: Enforceability
    normalization_status: NormalizationStatus
    evidence: str
    evidence_preserved: bool
    mapping_status: MappingStatus
    mapping_target: str | None
    loss_reason: str | None


def build_skill_decomposition_report(
    *,
    run_id: str,
    units: Sequence[Mapping[str, object]],
    fixture_ids: Sequence[str] = (),
) -> dict[str, object]:
    normalized_units = [_normalize_unit(unit, index=index) for index, unit in enumerate(units)]
    normalized_units.sort(
        key=lambda item: (item["id"], item["source"], item["path"], item["locator"])
    )
    report: dict[str, object] = {
        "schema": SKILL_DECOMPOSITION_SCHEMA,
        "status": "report-only",
        "implementation_allowed": False,
        "run_id": _required_text(run_id, "run_id"),
        "units": normalized_units,
        "summary": _summary(normalized_units),
    }
    normalized_fixture_ids = sorted({value.strip() for value in fixture_ids if value.strip()})
    if normalized_fixture_ids:
        report["fixture_ids"] = normalized_fixture_ids
    validation = validate_skill_decomposition_report(report)
    if validation["passed"] is not True:
        errors = validation.get("errors")
        raise ValueError("invalid skill decomposition report: " + "; ".join(_strings(errors)))
    return report


def validate_skill_decomposition_report(report: Mapping[str, object]) -> dict[str, object]:
    errors: list[str] = []
    if report.get("schema") != SKILL_DECOMPOSITION_SCHEMA:
        errors.append(f"unsupported schema: {report.get('schema')}")
    if report.get("status") != "report-only":
        errors.append("status must be report-only")
    if report.get("implementation_allowed") is not False:
        errors.append("implementation_allowed must be false")
    if not isinstance(report.get("run_id"), str) or not str(report["run_id"]).strip():
        errors.append("run_id must be a non-empty string")

    raw_units = report.get("units")
    normalized_units: list[DecompositionUnit] = []
    if not isinstance(raw_units, list):
        errors.append("units must be a list")
    else:
        seen_ids: set[str] = set()
        for index, item in enumerate(raw_units):
            if not isinstance(item, Mapping):
                errors.append(f"units[{index}] must be an object")
                continue
            try:
                normalized = _normalize_unit(item, index=index)
            except ValueError as error:
                errors.append(str(error))
                continue
            if normalized["id"] in seen_ids:
                errors.append(f"units[{index}] duplicates id {normalized['id']}")
            seen_ids.add(normalized["id"])
            normalized_units.append(normalized)

    expected_summary = _summary(normalized_units)
    actual_summary = report.get("summary")
    if not isinstance(actual_summary, Mapping):
        errors.append("summary must be an object")
    else:
        for key, expected in expected_summary.items():
            if actual_summary.get(key) != expected:
                errors.append(f"summary.{key} must be {expected}")

    fixture_ids = report.get("fixture_ids")
    if fixture_ids is not None and (
        not isinstance(fixture_ids, list)
        or not all(isinstance(item, str) and item.strip() for item in fixture_ids)
    ):
        errors.append("fixture_ids must be a list of non-empty strings")

    return {
        "passed": not errors,
        "errors": errors,
        "unit_count": len(normalized_units),
    }


def persist_skill_decomposition_artifacts(
    *,
    repo_root: Path,
    run_id: str,
    report: Mapping[str, object],
    save: bool = True,
) -> dict[str, str]:
    validation = validate_skill_decomposition_report(report)
    if validation["passed"] is not True:
        errors = validation.get("errors")
        raise ValueError("invalid skill decomposition report: " + "; ".join(_strings(errors)))
    if not save:
        return {}
    run_dir = prepare_artifact_dir(repo_root, run_id)
    return write_skill_decomposition_artifacts(run_dir=run_dir, report=report)


def write_skill_decomposition_artifacts(
    *,
    run_dir: Path,
    report: Mapping[str, object],
) -> dict[str, str]:
    validation = validate_skill_decomposition_report(report)
    if validation["passed"] is not True:
        errors = validation.get("errors")
        raise ValueError("invalid skill decomposition report: " + "; ".join(_strings(errors)))
    json_path = run_dir / "skill-decomposition.json"
    markdown_path = run_dir / "skill-decomposition.md"
    write_json(json_path, dict(report))
    write_text(markdown_path, render_skill_decomposition_markdown(report))
    return {
        "skill_decomposition_json": str(json_path),
        "skill_decomposition_md": str(markdown_path),
    }


def render_skill_decomposition_markdown(report: Mapping[str, object]) -> str:
    summary = report.get("summary")
    lines = [
        "# Skill Decomposition Report",
        "",
        f"- Schema: `{report.get('schema', 'unknown')}`",
        f"- Status: `{report.get('status', 'unknown')}`",
        f"- Run: `{report.get('run_id', 'unknown')}`",
        "- Implementation allowed: `false`",
        "",
        "## Summary",
        "",
    ]
    if isinstance(summary, Mapping):
        for key in sorted(summary):
            lines.append(f"- {key}: `{summary[key]}`")
    else:
        lines.append("- unavailable")
    lines.extend(["", "## Evidence units", ""])
    units = report.get("units")
    if not isinstance(units, list) or not units:
        lines.append("- None")
        return "\n".join(lines).rstrip() + "\n"
    for item in units:
        if not isinstance(item, Mapping):
            continue
        lines.extend(
            [
                f"### {item.get('id', 'unknown')}",
                "",
                f"- Source: `{item.get('source', '')}`",
                f"- Revision: `{item.get('revision', '')}`",
                f"- Path: `{item.get('path', '')}`",
                f"- Locator: `{item.get('locator', '')}`",
                f"- Knowledge role: `{item.get('knowledge_role', '')}`",
                f"- Enforceability: `{item.get('enforceability', '')}`",
                f"- Normalization: `{item.get('normalization_status', '')}`",
                f"- Evidence preserved: `{str(item.get('evidence_preserved')).lower()}`",
                f"- Mapping: `{item.get('mapping_status', '')}`",
                f"- Loss reason: {item.get('loss_reason') or 'None'}",
                f"- Evidence: {item.get('evidence', '')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _normalize_unit(item: Mapping[str, object], *, index: int) -> DecompositionUnit:
    prefix = f"units[{index}]"
    unit_id = _required_text(item.get("id"), f"{prefix}.id")
    source = _required_text(item.get("source"), f"{prefix}.source")
    revision = _required_text(item.get("revision"), f"{prefix}.revision")
    path = _relative_path(item.get("path"), f"{prefix}.path")
    locator = _required_text(item.get("locator"), f"{prefix}.locator")
    knowledge_role = _required_choice(
        item.get("knowledge_role"), _KNOWLEDGE_ROLES, f"{prefix}.knowledge_role"
    )
    enforceability = _required_choice(
        item.get("enforceability"), _ENFORCEABILITY, f"{prefix}.enforceability"
    )
    normalization_status = _required_choice(
        item.get("normalization_status"), _NORMALIZATION_STATUS, f"{prefix}.normalization_status"
    )
    evidence = _required_text(item.get("evidence"), f"{prefix}.evidence")
    evidence_preserved = item.get("evidence_preserved")
    if not isinstance(evidence_preserved, bool):
        raise ValueError(f"{prefix}.evidence_preserved must be a boolean")
    mapping_status = _required_choice(
        item.get("mapping_status"), _MAPPING_STATUS, f"{prefix}.mapping_status"
    )
    mapping_target = item.get("mapping_target")
    if mapping_target is not None and (
        not isinstance(mapping_target, str) or not mapping_target.strip()
    ):
        raise ValueError(f"{prefix}.mapping_target must be a non-empty string or null")
    loss_reason = item.get("loss_reason")
    if loss_reason is not None and (not isinstance(loss_reason, str) or not loss_reason.strip()):
        raise ValueError(f"{prefix}.loss_reason must be a non-empty string or null")
    if mapping_status != "mapped" and loss_reason is None:
        raise ValueError(f"{prefix}.loss_reason is required for {mapping_status} mapping")
    if mapping_status == "mapped":
        loss_reason = None
    return {
        "id": unit_id,
        "source": source,
        "revision": revision,
        "path": path,
        "locator": locator,
        "knowledge_role": cast(KnowledgeRole, knowledge_role),
        "enforceability": cast(Enforceability, enforceability),
        "normalization_status": cast(NormalizationStatus, normalization_status),
        "evidence": evidence,
        "evidence_preserved": evidence_preserved,
        "mapping_status": cast(MappingStatus, mapping_status),
        "mapping_target": mapping_target.strip() if isinstance(mapping_target, str) else None,
        "loss_reason": loss_reason.strip() if isinstance(loss_reason, str) else None,
    }


def _summary(units: Sequence[DecompositionUnit]) -> dict[str, int]:
    mapped = sum(item["mapping_status"] == "mapped" for item in units)
    context_only = sum(item["mapping_status"] == "context_only" for item in units)
    unmapped = sum(item["mapping_status"] == "unmapped" for item in units)
    ambiguous = sum(item["mapping_status"] == "ambiguous" for item in units)
    preserved = sum(item["evidence_preserved"] for item in units)
    return {
        "source_units": len(units),
        "mapped_units": mapped,
        "context_only_units": context_only,
        "unmapped_units": unmapped,
        "ambiguous_units": ambiguous,
        "loss_units": context_only + unmapped + ambiguous,
        "evidence_preserved_units": preserved,
        "evidence_not_preserved_units": len(units) - preserved,
        "deterministic_units": sum(item["enforceability"] == "deterministic" for item in units),
        "agent_review_units": sum(item["enforceability"] == "agent_review" for item in units),
        "context_only_enforceability_units": sum(
            item["enforceability"] == "context_only" for item in units
        ),
    }


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _required_choice(value: object, choices: frozenset[str], field: str) -> str:
    text = _required_text(value, field)
    if text not in choices:
        raise ValueError(f"{field} must be one of {', '.join(sorted(choices))}")
    return text


def _relative_path(value: object, field: str) -> str:
    path = _required_text(value, field).replace("\\", "/")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ValueError(f"{field} must be a normalized relative POSIX path")
    return str(parsed)


def _strings(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []
