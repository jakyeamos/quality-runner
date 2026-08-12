from quality_runner.fleet.legibility_evidence import collect_freshness_evidence

AS_OF = "2026-08-11T00:00:00+00:00"


def test_freshness_accepts_repository_frontmatter_conventions() -> None:
    evidence = collect_freshness_evidence(
        {
            ".agents/context/README.md": "last_reviewed: 2026-08-10\n",
            "docs/development.md": "reviewed_at: 2026-08-09\n",
        },
        AS_OF,
    )

    assert evidence["status"] == "known"
    assert evidence["reviewed_paths"] == [
        ".agents/context/README.md",
        "docs/development.md",
    ]


def test_historical_report_dates_do_not_stale_live_controls() -> None:
    evidence = collect_freshness_evidence(
        {
            ".agents/context/README.md": "last_reviewed: 2026-08-10\n",
            "docs/terrace/report-history/old.md": "reviewed: 2026-01-01\n",
        },
        AS_OF,
    )

    assert evidence["status"] == "known"
    assert evidence["stale_paths"] == []
    assert evidence["reviewed_paths"] == [".agents/context/README.md"]


def test_current_control_review_outweighs_an_older_non_archived_report() -> None:
    evidence = collect_freshness_evidence(
        {
            ".agents/context/README.md": "last_reviewed: 2026-08-10\n",
            "docs/REPORT-CARD.md": "Last updated: 2026-04-29\n",
        },
        AS_OF,
    )

    assert evidence["status"] == "known"
    assert evidence["stale_paths"] == ["docs/REPORT-CARD.md"]
