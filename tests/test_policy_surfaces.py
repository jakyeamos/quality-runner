from __future__ import annotations

import json
from pathlib import Path

from quality_runner.policy_surfaces import (
    classify_policy_surface,
    validate_policy_surfaces,
)


def test_policy_files_are_classified_outside_source_line_coverage() -> None:
    result = classify_policy_surface("./.quality-runner.toml")

    assert result == {
        "path": ".quality-runner.toml",
        "surface_kind": "policy_config",
        "validator": "quality-runner-config",
        "source_line_coverage": "not_applicable",
        "coverage_disposition": "validated_by_policy_gate",
    }
    assert classify_policy_surface("quality_runner/config.py") is None


def test_policy_surface_report_validates_each_artifact_and_keeps_inventory(tmp_path: Path) -> None:
    (tmp_path / ".pre-cr.json").write_text(
        json.dumps(
            {
                "version": 1,
                "testCommand": "pytest",
                "coveragePaths": ["coverage.lcov"],
                "threshold": 80,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner]\ndefault_profile = 'default'\n",
        encoding="utf-8",
    )
    (tmp_path / ".gitleaks.toml").write_text(
        "title = 'secret scan policy'\n",
        encoding="utf-8",
    )

    report = validate_policy_surfaces(tmp_path)

    assert report["status"] == "passed"
    assert report["scan_inventory"]["policy_files_considered"] == 3
    assert report["scan_inventory"]["source_line_coverage_excluded"] == [
        ".gitleaks.toml",
        ".pre-cr.json",
        ".quality-runner.toml",
    ]
    assert all(
        item["coverage_disposition"] == "validated_by_policy_gate"
        and item["source_line_coverage"] == "not_applicable"
        for item in report["surfaces"]
    )


def test_invalid_policy_is_a_blocking_policy_gate_failure(tmp_path: Path) -> None:
    (tmp_path / ".pre-cr.json").write_text('{"version": 1}', encoding="utf-8")

    report = validate_policy_surfaces(tmp_path, paths=[".pre-cr.json"])

    assert report["status"] == "failed"
    assert report["surfaces"][0]["status"] == "failed"
    assert "coveragePaths" in report["surfaces"][0]["errors"][0]


def test_deleted_policy_path_is_not_silently_dropped(tmp_path: Path) -> None:
    report = validate_policy_surfaces(tmp_path, paths=[".quality-runner.toml"])

    assert report["status"] == "failed"
    assert report["surfaces"][0]["path"] == ".quality-runner.toml"
    assert "missing" in report["surfaces"][0]["errors"][0]


def test_pre_cr_wires_policy_validation_and_excludes_only_source_coverage() -> None:
    root = Path(__file__).resolve().parents[1]
    config = json.loads((root / ".pre-cr.json").read_text(encoding="utf-8"))

    adapter = next(
        item for item in config["qualityAdapters"] if item["name"] == "policy-surface-validation"
    )
    assert adapter["required"] is True
    assert "check_policy_surfaces.py" in adapter["command"]
    assert ".quality-runner.toml" in config["excludePatterns"]
    assert "change-surface-matrix.json" in config["excludePatterns"]
