from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quality_runner.fleet.audit import fleet_audit_payload, fleet_replay_payload
from quality_runner.fleet.maturity_feed import build_maturity_feed
from quality_runner.fleet.strict_debt import (
    assess_strict_policy_visibility,
    assess_strict_type_debt,
)


def _write_policy(root: Path, occurrences: int) -> None:
    (root / "pyrightconfig.strict.json").write_text(
        '{"typeCheckingMode": "strict"}\n', encoding="utf-8"
    )
    baseline = {
        "schema": "quality-runner-basedpyright-strict-baseline-v0.1",
        "tool": "basedpyright",
        "baseline_ref": "fixture-ref",
        "coverage": {"state": "complete", "diagnostics_reported": occurrences},
        "legacy": {"state": "blocked" if occurrences else "clear", "occurrences": occurrences},
    }
    path = root / "docs/baselines/basedpyright-strict.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(baseline), encoding="utf-8")


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "dev"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "strict-debt-tests@example.com"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Strict Debt Tests"], cwd=root, check=True)
    (root / "README.md").write_text("# Strict debt fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=root, check=True, capture_output=True)


def test_strict_debt_is_not_applicable_without_a_policy(tmp_path: Path) -> None:
    result = assess_strict_type_debt(tmp_path)

    assert result["status"] == "not_applicable"
    assert result["score"] is None


def test_strict_policy_is_not_applicable_without_a_type_surface(tmp_path: Path) -> None:
    result = assess_strict_policy_visibility(tmp_path, {})

    assert result["status"] == "not_applicable"
    assert result["score"] is None


def test_strict_policy_rewards_visible_config_and_baseline(tmp_path: Path) -> None:
    _write_policy(tmp_path, 4154)

    result = assess_strict_policy_visibility(tmp_path, {})

    assert result["status"] == "validated"
    assert result["score"] == 4


def test_strict_policy_exposes_a_missing_config_for_basedpyright(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.basedpyright]\n", encoding="utf-8")

    result = assess_strict_policy_visibility(tmp_path, {})

    assert result["status"] == "absent"
    assert result["score"] == 1


def test_strict_policy_accepts_basedpyright_pyproject_config(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.basedpyright]\ntypeCheckingMode = "strict"\n', encoding="utf-8"
    )

    result = assess_strict_policy_visibility(tmp_path, {})

    assert result["status"] == "validated"
    assert result["score"] == 3


def test_basedpyright_command_accepts_pyright_pyproject_config(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pyright]\ntypeCheckingMode = "strict"\n', encoding="utf-8"
    )

    result = assess_strict_policy_visibility(
        tmp_path,
        {"quality_commands": [{"command": "uv run basedpyright src"}]},
    )

    assert result["status"] == "validated"
    assert result["score"] == 3
    assert "BasedPyright" in result["message"]


def test_strict_policy_accepts_typescript_strict_config(tmp_path: Path) -> None:
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions": {"strict": true}}\n', encoding="utf-8"
    )

    result = assess_strict_policy_visibility(tmp_path, {})

    assert result["status"] == "validated"
    assert result["score"] == 3


def test_strict_policy_accepts_mypy_strict_config(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.mypy]\nstrict = true\n", encoding="utf-8")

    result = assess_strict_policy_visibility(tmp_path, {})

    assert result["status"] == "validated"
    assert result["score"] == 3


def test_strict_debt_uses_bounded_occurrence_bands(tmp_path: Path) -> None:
    _write_policy(tmp_path, 4154)

    result = assess_strict_type_debt(tmp_path)

    assert result["status"] == "tracked"
    assert result["score"] == 0
    assert "4,154" in result["message"]
    assert any("occurrences=4154" in item["detail"] for item in result["evidence"])


def test_strict_debt_reaches_full_maturity_only_when_clear(tmp_path: Path) -> None:
    _write_policy(tmp_path, 0)

    result = assess_strict_type_debt(tmp_path)

    assert result["status"] == "validated"
    assert result["score"] == 4


def test_strict_debt_blocks_a_partial_policy(tmp_path: Path) -> None:
    (tmp_path / "pyrightconfig.strict.json").write_text(
        '{"typeCheckingMode": "strict"}\n', encoding="utf-8"
    )

    result = assess_strict_type_debt(tmp_path)

    assert result["status"] == "blocked"
    assert result["score"] == 0


def test_strict_debt_reaches_the_maturity_feed(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    root = projects / "fixture"
    _init_repo(root)
    _write_policy(root, 4154)

    result = fleet_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "fleet",
        as_of="2026-08-09T23:00:00+00:00",
    )
    artifact_root = Path(str(result["artifact_root"]))
    feed = build_maturity_feed(
        artifact_root,
        replay=fleet_replay_payload(output_dir=artifact_root),
    )

    repository = feed["repositories"][0]
    assert repository["dimension_scores"]["strict_policy_visibility"] == 4.0
    assert repository["dimension_scores"]["strict_type_debt"] == 0.0
    assert feed["dimension_means"]["strict_policy_visibility"] == 4.0
    assert feed["dimension_means"]["strict_type_debt"] == 0.0
    assert any(gap["dimension"] == "strict_type_debt" for gap in repository["dimension_gaps"])
