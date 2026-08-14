from __future__ import annotations

from pathlib import Path

from quality_runner.fleet.maturity_dimensions import (
    SPECIAL_MATURITY_DIMENSIONS,
    assess_maturity_dimensions,
)


def _assess(
    root: Path,
    *,
    scan: dict[str, object] | None = None,
    documents: dict[str, str] | None = None,
) -> dict[str, dict[str, object]]:
    return assess_maturity_dimensions(
        root=root,
        repository={"repo_id": "fixture", "primary_path": str(root)},
        scan=dict(scan or {}),
        documents=dict(documents or {}),
        config={},
        as_of="2026-08-13T12:00:00+00:00",
    )


def test_all_special_dimensions_have_explicit_applicability(tmp_path: Path) -> None:
    assessments = _assess(tmp_path)

    assert set(assessments) == SPECIAL_MATURITY_DIMENSIONS
    assert all(
        item["applicability"] in {"applicable", "not_applicable", "unknown"}
        for item in assessments.values()
    )
    assert {
        assessments[dimension]["applicability"]
        for dimension in (
            "accessibility",
            "performance",
            "critical_user_journeys",
            "web_readiness",
        )
    } == {"not_applicable"}


def test_web_surface_activates_all_user_facing_capabilities(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<html lang="en"><head><title>Fixture</title></head>'
        '<body><h1>Fixture</h1><img src="fixture.png" alt="Fixture"></body></html>',
        encoding="utf-8",
    )

    assessments = _assess(tmp_path)

    for dimension in (
        "accessibility",
        "performance",
        "critical_user_journeys",
        "web_readiness",
    ):
        assert assessments[dimension]["applicability"] == "applicable"
        assert assessments[dimension]["score"] is not None


def test_stateful_service_activates_migration_and_runtime_capabilities(
    tmp_path: Path,
) -> None:
    assessments = _assess(
        tmp_path,
        scan={
            "languages": ["python"],
            "repo_surfaces": [
                {
                    "id": "db_migrations",
                    "kind": "database",
                    "path": "migrations",
                    "evidence": "migration directory",
                },
                {
                    "id": "service_runtime",
                    "kind": "runtime",
                    "path": "src/service.py",
                    "evidence": "service entry point",
                },
            ],
            "quality_commands": [
                {"id": "tests", "command": "pytest", "source": "pyproject.toml"},
                {
                    "id": "runtime_smoke",
                    "command": "python -m service --check",
                    "source": "pyproject.toml",
                },
            ],
        },
        documents={
            "README.md": (
                "Migration rollback preserves data integrity. The service exposes a "
                "health check with metrics, logging, and tracing."
            )
        },
    )

    assert assessments["data_integrity_migration"]["applicability"] == "applicable"
    assert assessments["compatibility_migration"]["applicability"] == "applicable"
    assert assessments["observability_runtime_health"]["applicability"] == "applicable"
