from __future__ import annotations

import json
import subprocess
from pathlib import Path

from quality_runner.artifacts import ArtifactPolicy, cleanup_artifacts
from quality_runner.repo_hygiene import check_repo_hygiene


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _commit(repo: Path) -> None:
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.email=quality-runner@example.com",
        "-c",
        "user.name=Quality Runner",
        "commit",
        "-m",
        "fixture",
    )


def test_tracked_generated_output_and_ambiguous_build_source_are_distinguished(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("dist/\n", encoding="utf-8")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "app.js").write_text("bundle\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "esbuild.mjs").write_text("export default {};\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "fixture.json").write_text("{}\n", encoding="utf-8")
    _git(tmp_path, "add", "-f", "dist/app.js")
    _commit(tmp_path)

    report = check_repo_hygiene(tmp_path)

    assert report["schema"] == "repo-hygiene-v1"
    assert report["status"] == "fail"
    assert [item["path"] for item in report["generated_paths"]] == ["dist/app.js"]
    assert report["generated_paths"][0]["ignore_covered"] is True
    assert report["missing_ignore_rules"] == []
    assert not any(item["path"] == "build/esbuild.mjs" for item in report["generated_paths"])
    assert any(
        item["code"] == "ambiguous-directory-preserved" and item["path"] == "build/esbuild.mjs"
        for item in report["exceptions"]
    )


def test_missing_ignore_rule_is_reported_without_writing(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "coverage").mkdir()
    (tmp_path / "coverage" / "index.html").write_text("coverage\n", encoding="utf-8")
    _commit(tmp_path)

    report = check_repo_hygiene(tmp_path)

    assert report["status"] == "fail"
    assert report["missing_ignore_rules"] == [
        {
            "code": "test-coverage-output",
            "paths": ["coverage/index.html"],
            "reason": "confirmed generated output is not covered by Git ignore rules",
            "rule": "coverage/",
        }
    ]
    assert not (tmp_path / ".gitignore").exists()


def test_pnpm_state_detects_conflicts_and_accepts_explicit_exception(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "fixture", "packageManager": "npm@10.0.0"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    _commit(tmp_path)

    report = check_repo_hygiene(tmp_path)

    assert report["package_manager"]["status"] == "noncompliant"
    codes = {item["code"] for item in report["violations"]}
    assert {
        "pnpm-lockfile-missing",
        "package-manager-lock-conflict",
        "pnpm-version-pin-missing",
    } <= codes


def test_pnpm_workspace_candidate_is_reported_but_not_created(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "product", "packageManager": "pnpm@11.9.0"}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    package_dir = tmp_path / "packages" / "core"
    package_dir.mkdir(parents=True)
    (package_dir / "package.json").write_text(
        json.dumps({"name": "@product/core"}) + "\n", encoding="utf-8"
    )
    _commit(tmp_path)

    report = check_repo_hygiene(tmp_path)

    assert report["package_manager"]["status"] == "compliant"
    assert report["workspace"]["clear_product_workspace"] is True
    assert any(item["code"] == "pnpm-workspace-file-missing" for item in report["violations"])
    assert not (tmp_path / "pnpm-workspace.yaml").exists()


def test_default_quality_runner_retention_is_three_runs_and_fourteen_days() -> None:
    policy = ArtifactPolicy.from_config({})

    assert policy.retention_runs == 3
    assert policy.retention_days == 14
    assert policy.retention_enabled is True


def test_retention_preserves_blocked_runs_in_preview(tmp_path: Path) -> None:
    runs = tmp_path / ".quality-runner" / "runs"
    old = runs / "old"
    blocked = runs / "blocked-run"
    old.mkdir(parents=True)
    blocked.mkdir()
    (blocked / "run-summary.json").write_text('{"lifecycle_status":"blocked"}\n', encoding="utf-8")
    old.touch()
    blocked.touch()
    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner.artifacts]\nretention_runs = 1\nretention_days = 1\n",
        encoding="utf-8",
    )
    import os

    os.utime(old, (100, 100))
    os.utime(blocked, (200, 200))

    result = cleanup_artifacts(tmp_path, apply=False, now=10_000)

    assert result["preserved_run_ids"] == ["blocked-run"]
    assert result["would_delete_run_ids"] == ["old"]
