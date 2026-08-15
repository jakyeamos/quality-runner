from quality_runner.code_quality_findings import CATEGORY_ORDER, _counts


def test_category_summary_is_open_to_native_skill_and_future_categories() -> None:
    categories = [
        "maintenance-surface",
        "speed",
        "skill:performance-readiness",
        "future-category",
    ]

    counts = _counts(
        [{"category": category} for category in categories],
        "category",
        CATEGORY_ORDER,
    )

    assert counts["maintenance-surface"] == 1
    assert counts["speed"] == 1
    assert counts["skill:performance-readiness"] == 1
    assert counts["future-category"] == 1
    assert counts["debloat"] == 0
