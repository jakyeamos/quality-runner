from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from quality_runner.fleet.contracts import FRESHNESS_DAYS, MAX_DOCUMENT_BYTES, relative_path

MATRIX_SCHEMA = "change-surface-matrix/v1"
POINTER_SCHEMA = "change-surface-pointer/v1"
SURFACE_DISTRIBUTIONS = {"public_core", "public_adapter", "local_only"}
REPOSITORY_MATRIX_PATHS = (
    ".agents/change-surface-matrix.json",
    ".context/change-surface-matrix.json",
    "docs/change-surface-matrix.json",
    "change-surface-matrix.json",
)
SKILL_MATRIX_GLOB = "skills/*/change-surface-matrix.json"


def assess_change_surface_coverage(
    root: Path,
    documents: dict[str, str],
    as_of: str,
) -> dict[str, Any]:
    """Assess existing matrix evidence without creating or modifying it."""
    candidates = [root / relative for relative in REPOSITORY_MATRIX_PATHS]
    repository_matrix = next((path for path in candidates if path.is_file()), None)
    skill_matrices = sorted(path for path in root.glob(SKILL_MATRIX_GLOB) if path.is_file())
    if repository_matrix is None:
        if skill_matrices:
            return _result(
                score=2,
                status="partial",
                message=(
                    "Scoped skill matrices exist, but no repository-wide change-surface "
                    "contract covers this repository."
                ),
                evidence=[
                    {
                        "path": relative_path(root, path),
                        "detail": "Skill-scoped matrix; not repository-wide coverage.",
                    }
                    for path in skill_matrices[:12]
                ],
            )
        combined = "\n".join(documents.values()).lower()
        terms = ("change surface", "change matrix", "dependency map", "propagation path")
        if any(term in combined for term in terms):
            return _result(
                score=1,
                status="prose_only",
                message=(
                    "Dependency or change-surface prose exists without structured ownership "
                    "and operation coverage."
                ),
                evidence=[
                    {
                        "path": path,
                        "detail": "Generic dependency or propagation language was found.",
                    }
                    for path, content in sorted(documents.items())
                    if any(term in content.lower() for term in terms)
                ][:12],
            )
        return _result(
            score=0,
            status="missing",
            message="No repository-owned change-surface matrix or validated pointer was found.",
            evidence=[
                {
                    "path": REPOSITORY_MATRIX_PATHS[0],
                    "detail": "Expected repository contract location.",
                }
            ],
        )
    return assess_matrix_path(repository_matrix, root=root, as_of=as_of)


def assess_matrix_path(path: Path, *, root: Path, as_of: str) -> dict[str, Any]:
    display_path = relative_path(root, path)
    try:
        if path.is_symlink():
            return _unknown(display_path, "Matrix path is a symlink and was not followed.")
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            return _unknown(display_path, "Matrix exceeds the bounded audit size.")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return _unknown(display_path, f"Matrix is unreadable or invalid JSON: {error}")
    if not isinstance(payload, dict):
        return _unknown(display_path, "Matrix root must be an object.")
    payload = cast(dict[str, Any], payload)

    if payload.get("schema_version") == POINTER_SCHEMA:
        target = payload.get("artifact_path")
        if not isinstance(target, str) or not target.strip():
            return _unknown(display_path, "External pointer does not name an artifact_path.")
        target_path = Path(target).expanduser()
        if not target_path.is_absolute():
            target_path = path.parent / target_path
        resolved = target_path.resolve()
        if resolved == path.resolve():
            return _unknown(display_path, "External pointer resolves to itself.")
        result = assess_matrix_path(resolved, root=root, as_of=as_of)
        result["evidence"].insert(
            0,
            {
                "path": display_path,
                "detail": f"Validated pointer to {relative_path(root, resolved)}.",
            },
        )
        return result

    if payload.get("schema_version") != MATRIX_SCHEMA:
        return _unknown(display_path, "Unsupported or missing matrix schema_version.")

    problems: list[str] = []
    owner = payload.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        problems.append("matrix owner is missing")
    subject = payload.get("subject")
    if not isinstance(subject, dict) or not isinstance(
        cast(dict[str, Any], subject).get("id"), str
    ):
        problems.append("subject identity is missing")
    reviewed = _parse_date(payload.get("last_reviewed"))
    as_of_date = _parse_date(as_of)
    if reviewed is None:
        problems.append("freshness is unknown")
    elif as_of_date is not None and as_of_date - reviewed > timedelta(days=FRESHNESS_DAYS):
        problems.append("matrix is stale")

    surfaces = payload.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        problems.append("surfaces are missing")
        surfaces = []
    applicable = 0
    local_declared = False
    external_declared = False
    unresolved = 0
    for index, surface in enumerate(cast(list[object], surfaces)):
        if not isinstance(surface, dict):
            problems.append(f"surface {index + 1} is invalid")
            unresolved += 1
            continue
        surface = cast(dict[str, Any], surface)
        status = surface.get("status", "applicable")
        scope = surface.get("scope")
        local_declared = local_declared or scope == "local"
        external_declared = external_declared or scope == "external"
        if status == "not_applicable":
            if not _nonempty(surface.get("reason")) or not _string_list(surface.get("evidence")):
                problems.append(f"surface {index + 1} has unsupported not_applicable status")
            continue
        applicable += 1
        operations = set(_string_list(surface.get("operations")))
        distribution = surface.get("distribution")
        if not _nonempty(surface.get("owner")):
            problems.append(f"surface {index + 1} owner is missing")
        if not _nonempty(surface.get("condition")):
            problems.append(f"surface {index + 1} condition is missing")
        if not _string_list(surface.get("validation")):
            problems.append(f"surface {index + 1} validation is missing")
        if operations != {"add", "change", "remove"}:
            problems.append(f"surface {index + 1} does not cover add/change/remove")
        if distribution not in SURFACE_DISTRIBUTIONS:
            problems.append(f"surface {index + 1} distribution is missing or unsupported")
        if distribution == "public_adapter" and not _string_list(surface.get("contract_fixtures")):
            problems.append(f"surface {index + 1} public adapter fixture is missing")
        if status in {"unknown", "unresolved", "stale", "contradictory"}:
            unresolved += 1
    if applicable and not local_declared:
        problems.append("known local relationships are not represented")
    if applicable and not external_declared:
        problems.append("known external relationships are not represented")

    declared_unresolved = payload.get("unresolved_surfaces")
    if isinstance(declared_unresolved, list) and declared_unresolved:
        unresolved += len(cast(list[object], declared_unresolved))
        problems.append("unresolved surfaces remain")

    operation_evidence = payload.get("operation_evidence")
    exercised = True
    if not isinstance(operation_evidence, dict):
        exercised = False
    else:
        operation_evidence = cast(dict[str, Any], operation_evidence)
        for operation in ("add", "change", "remove"):
            item = operation_evidence.get(operation)
            if (
                not isinstance(item, dict)
                or cast(dict[str, Any], item).get("status") != "passed"
                or not _string_list(cast(dict[str, Any], item).get("evidence"))
            ):
                exercised = False

    if problems:
        return _result(
            score=2,
            status="stale" if "matrix is stale" in problems else "incomplete",
            message=f"Structured matrix exists but {'; '.join(sorted(set(problems))[:4])}.",
            evidence=[
                {"path": display_path, "detail": detail} for detail in sorted(set(problems))[:12]
            ],
        )
    if not exercised or unresolved:
        return _result(
            score=3,
            status="validated",
            message=(
                "The matrix is current and validates known local and external relationships; "
                "add/change/remove proof is incomplete."
            ),
            evidence=[{"path": display_path, "detail": "Current validated matrix."}],
        )
    return _result(
        score=4,
        status="maintained",
        message="Add/change/remove behavior is evidenced and no applicable surface is unresolved.",
        evidence=[{"path": display_path, "detail": "Behaviorally exercised matrix."}],
    )


def _unknown(path: str, detail: str) -> dict[str, Any]:
    return _result(
        score=2,
        status="unknown",
        message="Structured matrix evidence is present but could not be validated.",
        evidence=[{"path": path, "detail": detail}],
    )


def _result(
    *, score: int | None, status: str, message: str, evidence: list[dict[str, str]]
) -> dict[str, Any]:
    return {"score": score, "status": status, "message": message, "evidence": evidence}


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[object], value) if isinstance(item, str) and item.strip()]


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
