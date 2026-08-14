from quality_runner.fleet.projection import build_local_projection


def test_projection_keeps_unknown_scores_in_remediation_without_crashing() -> None:
    projection = build_local_projection(
        {"repo_id": "repo-fixture"},
        [
            {"dimension": "cache_design", "status": "unknown", "score": None},
            {"dimension": "quality_commands", "status": "maintained", "score": 4},
        ],
    )

    assert "cache design and lifecycle" in projection["content"]
    assert "build, test, lint, and quality commands" not in projection["content"]
