from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ui_quality"


def _fixture(name: str) -> dict[str, object]:
    from quality_runner.ui_quality import load_ui_quality_fixture

    return load_ui_quality_fixture(FIXTURE_DIR / name)


def test_ui_contract_fixture_is_report_only_and_all_five_checks_pass() -> None:
    from quality_runner.ui_quality import (
        build_ui_quality_report,
        validate_ui_quality_report,
    )

    report = build_ui_quality_report(
        run_id="ui-contract-fixture",
        fixture=_fixture("semantic-modifier-contract.json"),
        fixture_path="tests/fixtures/ui_quality/semantic-modifier-contract.json",
    )

    checks = cast(list[Mapping[str, object]], report["checks"])
    summary = cast(Mapping[str, int], report["summary"])
    validation = validate_ui_quality_report(report)

    assert validation["passed"] is True
    assert report["status"] == "report-only"
    assert report["implementation_allowed"] is False
    assert report["scope"] == "fixture-only"
    assert report["result"] == "passed"
    assert len(checks) == 5
    assert all(check["enforceability"] == "deterministic" for check in checks)
    assert all(check["status"] == "passed" for check in checks)
    assert summary == {
        "check_count": 5,
        "passed_check_count": 5,
        "finding_count": 0,
        "deterministic_check_count": 5,
        "judgment_only_check_count": 0,
    }
    assert report["findings"] == []


def test_ui_regression_fixture_reports_ownership_theme_contrast_modifier_and_state_findings() -> (
    None
):
    from quality_runner.ui_quality import build_ui_quality_report

    report = build_ui_quality_report(
        run_id="ui-regression-fixture",
        fixture=_fixture("contrast-state-regressions.json"),
        fixture_path="tests/fixtures/ui_quality/contrast-state-regressions.json",
    )

    findings = cast(list[Mapping[str, object]], report["findings"])
    rule_ids = {str(finding["rule_id"]) for finding in findings}
    evidence = [str(finding["evidence"]) for finding in findings]
    checks = cast(list[Mapping[str, object]], report["checks"])

    assert report["status"] == "report-only"
    assert report["implementation_allowed"] is False
    assert report["result"] == "findings"
    assert {
        "ui-token-ownership-raw-semantic-value",
        "ui-token-ownership-component-bypass",
        "ui-theme-role-missing-theme",
        "ui-contrast-text",
        "ui-contrast-ui",
        "ui-modifier-dependency-omitted",
        "ui-state-missing-non-color-cue",
    } <= rule_ids
    assert any("< 4.50:1" in item for item in evidence)
    assert any("< 3.00:1" in item for item in evidence)
    assert {check["status"] for check in checks} == {"matched"}


def test_ui_quality_fixture_evaluation_does_not_write_artifacts(tmp_path: Path) -> None:
    from quality_runner.ui_quality import build_ui_quality_report

    build_ui_quality_report(
        run_id="ui-no-write",
        fixture=_fixture("semantic-modifier-contract.json"),
        fixture_path="tests/fixtures/ui_quality/semantic-modifier-contract.json",
    )

    assert not (tmp_path / ".quality-runner").exists()
