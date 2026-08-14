from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from quality_runner.fleet.change_matrix import (
    MATRIX_SCHEMA,
    POINTER_SCHEMA,
    REPOSITORY_MATRIX_PATHS,
    SKILL_MATRIX_GLOB,
    _nonempty,
    _parse_date,
    _result,
    _string_list,
    _unknown,
)
from quality_runner.fleet.contracts import (
    FRESHNESS_DAYS,
    MATRIX_MAINTENANCE_STANDARD,
    MAX_DOCUMENT_BYTES,
    relative_path,
)


def assess_matrix_maintenance(
    root: Path,
    documents: dict[str, str],
    as_of: str,
) -> dict[str, Any]:
    """Assess the repository's explicit matrix-maintenance policy surface.

    This is intentionally narrower than the full change-surface maturity rubric.
    It answers one question: does the repository's own matrix explicitly require
    itself to stay current when material features or functionality change, while
    preserving an evidenced not_applicable path?
    """
    candidates = [root / relative for relative in REPOSITORY_MATRIX_PATHS]
    repository_matrix = next((path for path in candidates if path.is_file()), None)
    if repository_matrix is None:
        skill_matrices = sorted(path for path in root.glob(SKILL_MATRIX_GLOB) if path.is_file())
        combined = "\n".join(documents.values()).lower()
        terms = ("change surface", "change matrix", "dependency map", "propagation path")
        if any(term in combined for term in terms):
            return _result(
                score=1,
                status="prose_only",
                message=(
                    "Change-surface or dependency prose exists, but no repository-owned "
                    "matrix declares the matrix-maintenance standard."
                ),
                evidence=[
                    {
                        "path": path,
                        "detail": "Prose mentions a change-surface concept without the required repository contract.",
                    }
                    for path, content in sorted(documents.items())
                    if any(term in content.lower() for term in terms)
                ][:12],
            )
        evidence = [
            {
                "path": REPOSITORY_MATRIX_PATHS[0],
                "detail": "Expected repository-owned change-surface matrix location.",
            }
        ]
        evidence.extend(
            {
                "path": relative_path(root, path),
                "detail": "Skill-scoped matrix does not satisfy the repository-wide standard.",
            }
            for path in skill_matrices[:12]
        )
        return _result(
            score=0,
            status="missing",
            message="No repository-owned matrix was found for the matrix-maintenance standard.",
            evidence=evidence,
        )

    loaded = _load_matrix_document(repository_matrix, root=root)
    if loaded.get("error"):
        return _unknown(str(loaded["display_path"]), str(loaded["error"]))
    payload = loaded.get("payload")
    display_path = str(loaded["display_path"])
    if not isinstance(payload, dict):
        return _unknown(display_path, "Matrix root must be an object.")
    if payload.get("schema_version") != MATRIX_SCHEMA:
        return _unknown(display_path, "Unsupported or missing matrix schema_version.")

    problems: list[str] = []
    if not _nonempty(payload.get("owner")):
        problems.append("matrix owner is missing")
    subject = payload.get("subject")
    if not isinstance(subject, dict) or not _nonempty(subject.get("id")):
        problems.append("subject identity is missing")
    reviewed = _parse_date(payload.get("last_reviewed"))
    as_of_date = _parse_date(as_of)
    if reviewed is None:
        problems.append("freshness is unknown")
    elif as_of_date is not None and as_of_date - reviewed > timedelta(days=FRESHNESS_DAYS):
        problems.append("matrix is stale")

    surfaces = payload.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        return _result(
            score=2,
            status="stale" if "matrix is stale" in problems else "incomplete",
            message="The repository matrix does not contain a usable surfaces list.",
            evidence=_problem_evidence(display_path, problems or ["surfaces are missing"]),
        )
    maintenance = next(
        (
            surface
            for surface in surfaces
            if isinstance(surface, dict) and surface.get("id") == MATRIX_MAINTENANCE_STANDARD
        ),
        None,
    )
    if maintenance is None:
        return _result(
            score=2,
            status="stale" if "matrix is stale" in problems else "incomplete",
            message=(
                "The repository matrix is present, but it does not declare the "
                "matrix-maintenance standard."
            ),
            evidence=_problem_evidence(
                display_path,
                problems + [f"missing surface id {MATRIX_MAINTENANCE_STANDARD}"],
            ),
        )

    if not isinstance(maintenance, dict):
        return _result(
            score=2,
            status="incomplete",
            message="The matrix-maintenance surface is not an object.",
            evidence=[{"path": display_path, "detail": "matrix-maintenance surface is invalid"}],
        )
    if problems:
        return _result(
            score=2,
            status="stale" if "matrix is stale" in problems else "incomplete",
            message=f"Matrix-maintenance evidence is incomplete: {'; '.join(sorted(set(problems))[:4])}.",
            evidence=_problem_evidence(display_path, problems),
        )
    if maintenance.get("status") == "not_applicable":
        if not _nonempty(maintenance.get("reason")) or not _string_list(
            maintenance.get("evidence")
        ):
            return _result(
                score=2,
                status="incomplete",
                message=(
                    "The matrix-maintenance surface is marked not_applicable without a "
                    "non-empty reason and evidence list."
                ),
                evidence=[
                    {
                        "path": display_path,
                        "detail": "not_applicable requires both reason and evidence.",
                    }
                ],
            )
        return _result(
            score=None,
            status="not_applicable",
            message="The repository explicitly documents why matrix maintenance is not applicable.",
            evidence=[
                {"path": display_path, "detail": str(maintenance["reason"])},
                *[
                    {"path": display_path, "detail": item}
                    for item in _string_list(maintenance.get("evidence"))[:12]
                ],
            ],
        )

    if maintenance.get("status") in {"unknown", "unresolved", "stale", "contradictory"}:
        problems.append(f"matrix-maintenance surface status is {maintenance['status']}")
    if not _nonempty(maintenance.get("owner")):
        problems.append("matrix-maintenance owner is missing")
    condition = str(maintenance.get("condition", "")).lower()
    if not (
        "material" in condition
        and "change" in condition
        and any(term in condition for term in ("feature", "functionality"))
    ):
        problems.append(
            "matrix-maintenance condition does not cover material feature or functionality changes"
        )
    validation = " ".join(_string_list(maintenance.get("validation"))).lower()
    if not _string_list(maintenance.get("validation")):
        problems.append("matrix-maintenance validation is missing")
    if "same change" not in validation or "update" not in validation:
        problems.append(
            "matrix-maintenance validation does not require a same-change matrix update"
        )
    if not ("no-impact" in validation or "no impact" in validation) or "reason" not in validation:
        problems.append(
            "matrix-maintenance validation does not require a reviewed no-impact reason"
        )
    if set(_string_list(maintenance.get("operations"))) != {"add", "change", "remove"}:
        problems.append("matrix-maintenance does not cover add/change/remove")

    if problems:
        return _result(
            score=2,
            status="stale" if "matrix is stale" in problems else "incomplete",
            message=f"Matrix-maintenance evidence is incomplete: {'; '.join(sorted(set(problems))[:4])}.",
            evidence=_problem_evidence(display_path, problems),
        )

    operation_evidence = payload.get("operation_evidence")
    exercised = isinstance(operation_evidence, dict) and all(
        isinstance(operation_evidence.get(operation), dict)
        and operation_evidence[operation].get("status") == "passed"
        and _string_list(operation_evidence[operation].get("evidence"))
        for operation in ("add", "change", "remove")
    )
    return _result(
        score=4 if exercised else 3,
        status="maintained" if exercised else "current",
        message=(
            "The matrix explicitly requires same-change maintenance and reviewed no-impact "
            "decisions, with add/change/remove evidence."
            if exercised
            else "The matrix explicitly requires same-change maintenance and reviewed no-impact decisions."
        ),
        evidence=[{"path": display_path, "detail": "Current matrix-maintenance policy surface."}],
    )


def _load_matrix_document(
    path: Path, *, root: Path, visited: set[Path] | None = None
) -> dict[str, Any]:
    display_path = relative_path(root, path)
    visited_paths = visited or set()
    resolved_path = path.resolve()
    if resolved_path in visited_paths:
        return {"display_path": display_path, "error": "Matrix pointer cycle detected."}
    visited_paths.add(resolved_path)
    try:
        if path.is_symlink():
            return {
                "display_path": display_path,
                "error": "Matrix path is a symlink and was not followed.",
            }
        if path.stat().st_size > MAX_DOCUMENT_BYTES:
            return {"display_path": display_path, "error": "Matrix exceeds the bounded audit size."}
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {
            "display_path": display_path,
            "error": f"Matrix is unreadable or invalid JSON: {error}",
        }
    if not isinstance(payload, dict):
        return {"display_path": display_path, "error": "Matrix root must be an object."}
    if payload.get("schema_version") != POINTER_SCHEMA:
        return {"display_path": display_path, "payload": payload}
    target = payload.get("artifact_path")
    if not isinstance(target, str) or not target.strip():
        return {
            "display_path": display_path,
            "error": "External pointer does not name an artifact_path.",
        }
    target_path = Path(target).expanduser()
    if not target_path.is_absolute():
        target_path = path.parent / target_path
    loaded = _load_matrix_document(target_path, root=root, visited=visited_paths)
    if loaded.get("error"):
        return loaded
    loaded.setdefault("evidence", []).insert(
        0,
        {
            "path": display_path,
            "detail": f"Validated pointer to {relative_path(root, target_path.resolve())}.",
        },
    )
    return loaded


def _problem_evidence(path: str, problems: list[str]) -> list[dict[str, str]]:
    return [{"path": path, "detail": detail} for detail in sorted(set(problems))[:12]]
