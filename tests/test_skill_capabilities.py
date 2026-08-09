from __future__ import annotations

import json
from pathlib import Path

import pytest

from quality_runner.skill_capabilities import (
    CAPABILITY_SCHEMA,
    _string_list,
    build_skill_capabilities,
    build_skill_capability_feed,
    load_quality_scan,
    write_skill_capability_feed,
)


def test_debloat_is_represented_as_a_finding_source_without_a_scalar_score() -> None:
    records = build_skill_capabilities(
        quality_scan={
            "run_id": "run-1",
            "skill_coverage": [],
            "findings": [
                {"category": "debloat", "rule_id": "large-source-file"},
            ],
        }
    )

    debloat = next(item for item in records if item["id"] == "debloat-repository")
    assert debloat["finding_expectation"] == "required"
    assert debloat["quality_runner"]["status"] == "scan_observed"
    assert debloat["quality_runner"]["coverage"]["finding_count"] == 1
    assert debloat["backfill"]["mode"] == "report_and_plan"
    assert "score" not in debloat


def test_active_quality_skill_reports_coverage_and_keeps_apply_owner_controlled() -> None:
    records = build_skill_capabilities(
        quality_skills=[
            {
                "id": "security-review",
                "name": "Security review",
                "version": "1.0.0",
                "content_sha256": "abc",
                "deterministic_rules": [
                    {
                        "id": "no-debug",
                        "type": "disallowed_pattern",
                    }
                ],
            }
        ],
        skill_coverage=[
            {
                "skill_id": "security-review",
                "rule_id": "no-debug",
                "rule_type": "disallowed_pattern",
                "status": "evaluated",
                "finding_count": 0,
            }
        ],
        quality_scan={"skill_coverage": [], "findings": []},
    )

    skill = next(item for item in records if item["id"] == "security-review")
    assert skill["finding_expectation"] == "required"
    assert skill["quality_runner"]["status"] == "coverage_proven"
    assert skill["backfill"]["phases"][2]["state"] == "available"
    assert skill["backfill"]["phases"][3]["state"] == "unsupported"


def test_capability_feed_can_be_written_for_pronto(tmp_path: Path) -> None:
    scan = {
        "run_id": "run-2",
        "quality_skills": [],
        "skill_coverage": [],
        "findings": [],
    }
    feed = build_skill_capability_feed(scan)
    assert feed["schema"] == CAPABILITY_SCHEMA
    assert feed["status"] == "report_only"

    output = tmp_path / "capabilities.json"
    result = write_skill_capability_feed(scan, output)
    assert result["status"] == "written"
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == CAPABILITY_SCHEMA


def test_agent_review_and_incomplete_coverage_remain_explicit() -> None:
    records = build_skill_capabilities(
        quality_skills=[
            {
                "id": "review-only",
                "agent_reviews": [{"id": "human", "category": "security"}],
            },
            {
                "id": "no-coverage",
                "deterministic_rules": [{"id": "rule", "type": "pattern"}],
            },
        ],
        skill_coverage=[
            {
                "skill_id": "review-only",
                "status": "review_required",
                "finding_count": "not-a-number",
            },
            {"skill_id": "review-only", "status": "skipped", "finding_count": 2},
        ],
        quality_scan={"skill_coverage": [], "findings": []},
    )

    review = next(item for item in records if item["id"] == "review-only")
    assert review["finding_classes"] == [
        {
            "id": "human",
            "label": "security: human",
            "state": "review_required",
            "evidence": "Declared agent review; a review report is required for findings.",
        }
    ]
    assert review["quality_runner"]["status"] == "configured"
    assert review["quality_runner"]["coverage"]["finding_count"] == 2
    assert review["quality_runner"]["gaps"]
    assert review["backfill"]["phases"][4]["state"] == "required"

    no_coverage = next(item for item in records if item["id"] == "no-coverage")
    assert no_coverage["quality_runner"]["status"] == "configured"
    assert "no deterministic or agent-review coverage" in no_coverage["quality_runner"]["gaps"][0]


def test_active_skill_without_a_scan_reports_a_configuration_gap() -> None:
    records = build_skill_capabilities(
        quality_skills=[
            {
                "id": "configured-only",
                "deterministic_rules": [{"id": "rule", "type": "pattern"}],
            }
        ]
    )

    skill = next(item for item in records if item["id"] == "configured-only")
    assert skill["quality_runner"]["status"] == "configured"
    assert skill["quality_runner"]["coverage"]["rule_count"] == 0
    assert "No run-specific coverage" in skill["quality_runner"]["gaps"][0]


def test_empty_active_skill_and_missing_inventory_stay_not_evidenced() -> None:
    records = build_skill_capabilities(
        quality_skills=[{"id": "empty", "name": "Empty", "deterministic_rules": [], "agent_reviews": []}]
    )
    empty = next(item for item in records if item["id"] == "empty")
    assert empty["finding_expectation"] == "review_required"
    assert empty["backfill"]["mode"] == "not_evidenced"
    assert empty["quality_runner"]["status"] == "configured"

    native_only = build_skill_capabilities()
    debloat = next(item for item in native_only if item["id"] == "debloat-repository")
    assert debloat["quality_runner"]["status"] == "adapter_defined"
    assert any("No active Quality Runner skill packs" in gap for gap in debloat["quality_runner"]["gaps"])


def test_feed_preserves_supplied_capabilities_and_rejects_invalid_inputs(tmp_path: Path) -> None:
    supplied = build_skill_capability_feed(
        {"run_id": "run-3", "skill_capabilities": [{"id": "already-built"}]}
    )
    assert supplied["skills"] == [{"id": "already-built"}]
    assert supplied["run_id"] == "run-3"

    with pytest.raises(ValueError, match="JSON object"):
        build_skill_capability_feed([])  # type: ignore[arg-type]

    valid = tmp_path / "valid.json"
    valid.write_text('{"run_id": "run-4"}\n', encoding="utf-8")
    assert load_quality_scan(valid)["run_id"] == "run-4"

    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        load_quality_scan(invalid)


def test_string_list_discards_non_strings_and_blank_values() -> None:
    assert _string_list(["one", "", " two ", 3]) == ["one", " two "]
    assert _string_list("one") == []
