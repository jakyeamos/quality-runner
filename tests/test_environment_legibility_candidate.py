from __future__ import annotations

from pathlib import Path

from quality_runner.skill_ingest import validate_skill_pack


def test_environment_legibility_candidate_validates() -> None:
    repository = Path(__file__).parents[1]
    result = validate_skill_pack(
        repository / "docs/skill-candidates/environment-legibility.toml",
        skill_id="environment-legibility",
        repo_root=repository,
    )

    assert result["status"] == "validated"
    assert result["warnings"] == []
    assert result["errors"] == []
