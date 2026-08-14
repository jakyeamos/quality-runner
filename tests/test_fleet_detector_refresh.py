from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from quality_runner.fleet.detector_refresh import fleet_detector_refresh_payload
from quality_runner.workflow import refresh_payload

ROOT = Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(root: Path, *, branch: str = "dev") -> None:
    root.mkdir()
    _git(root, "init", "-b", branch)
    _git(root, "config", "user.email", "qr@example.test")
    _git(root, "config", "user.name", "QR Test")
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "fixture")


def _fake_refresh(**kwargs: Any) -> dict[str, Any]:
    root = Path(kwargs["repo_root"])
    prefix = str(kwargs["run_id_prefix"])
    for suffix in ("inspect", "run", "verify"):
        run_dir = root / ".quality-runner" / "runs" / f"{prefix}-{suffix}"
        run_dir.mkdir(parents=True)
        (run_dir / "run-manifest.json").write_text(
            json.dumps(
                {
                    "git": {"branch": "HEAD", "commit": _git(root, "rev-parse", "HEAD")},
                    "repo_root": str(root),
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "code-quality-scan.json").write_text(
            json.dumps({"findings": [{"id": "fixture"}], "coverage": "full"}),
            encoding="utf-8",
        )
    return {"status": "completed"}


def _contract_checked_fake_refresh(**kwargs: Any) -> dict[str, Any]:
    inspect.signature(refresh_payload).bind(**kwargs)
    return _fake_refresh(**kwargs)


def _fake_refresh_with_invalid_run(**kwargs: Any) -> dict[str, Any]:
    result = _fake_refresh(**kwargs)
    root = Path(kwargs["repo_root"])
    prefix = str(kwargs["run_id_prefix"])
    (root / ".quality-runner" / "runs" / f"{prefix}-run" / "run-manifest.json").write_text(
        "{not-json\n", encoding="utf-8"
    )
    return result


def _fake_refresh_with_missing_run(**kwargs: Any) -> dict[str, Any]:
    root = Path(kwargs["repo_root"])
    prefix = str(kwargs["run_id_prefix"])
    for suffix in ("inspect", "verify"):
        (root / ".quality-runner" / "runs" / f"{prefix}-{suffix}").mkdir(parents=True)
    return {
        "status": "blocked",
        "phase_timings": {
            "inspect": {"status": "completed"},
            "run": {"status": "timed-out"},
            "verify": {"status": "completed"},
        },
        "runs": {
            "inspect": {"run_id": f"{prefix}-inspect", "status": "completed"},
            "run": {
                "run_id": f"{prefix}-run",
                "status": "blocked",
                "reason": "refresh run phase exceeded the repository deadline",
                "timeout_scope": "repository",
                "timeout_seconds": 600,
            },
            "verify": {"run_id": f"{prefix}-verify", "status": "completed"},
        },
    }


def test_detector_refresh_scans_exact_target_and_publishes_normal_runs(tmp_path: Path) -> None:
    repo = tmp_path / "app"
    _init_repo(repo)
    _git(repo, "switch", "-c", "feature")
    (repo / "feature.txt").write_text("uncommitted\n", encoding="utf-8")
    feature_status = _git(repo, "status", "--porcelain=v1")
    dev_head = _git(repo, "rev-parse", "dev")

    payload = fleet_detector_refresh_payload(
        projects_root=tmp_path,
        repository_paths=[repo],
        target_overrides={str(repo): "dev"},
        output_dir=tmp_path / "artifacts",
        as_of="2026-08-14T04:45:00Z",
        refresh_callback=_contract_checked_fake_refresh,
    )

    assert payload["status"] == "completed"
    assert payload["counts"] == {"published": 1, "blocked": 0, "unsupported": 0}
    result = payload["results"][0]
    assert result["target"]["branch"] == "dev"
    assert result["target"]["head"] == dev_head
    assert result["finding_count"] == 1
    assert result["cleanup"]["status"] == "passed"
    final_status = _git(repo, "status", "--porcelain=v1")
    assert feature_status in final_status
    assert "?? .quality-runner/" in final_status
    manifest = json.loads(
        (Path(result["published_paths"][0]) / "run-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["git"]["branch"] == "dev"
    assert manifest["git"]["commit"] == dev_head
    assert manifest["repo_root"] == str(repo)


def test_detector_refresh_applies_repository_deadline_to_each_phase(tmp_path: Path) -> None:
    repo = tmp_path / "app"
    _init_repo(repo)
    captured: dict[str, Any] = {}

    def capture_refresh(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return _fake_refresh(**kwargs)

    fleet_detector_refresh_payload(
        projects_root=tmp_path,
        repository_paths=[repo],
        output_dir=tmp_path / "artifacts",
        timeout_seconds=900,
        as_of="2026-08-14T04:45:30Z",
        refresh_callback=capture_refresh,
    )

    assert captured["timeout_seconds"] == 120
    assert captured["inspect_timeout_seconds"] == 900
    assert captured["run_timeout_seconds"] == 900
    assert captured["verify_timeout_seconds"] == 900
    assert captured["total_timeout_seconds"] == 900


def test_detector_refresh_records_blocked_target_and_continues(tmp_path: Path) -> None:
    ambiguous = tmp_path / "ambiguous"
    ready = tmp_path / "ready"
    _init_repo(ambiguous, branch="main")
    _git(ambiguous, "branch", "other")
    _init_repo(ready)

    payload = fleet_detector_refresh_payload(
        projects_root=tmp_path,
        repository_paths=[ambiguous, ready],
        output_dir=tmp_path / "artifacts",
        as_of="2026-08-14T04:46:00Z",
        refresh_callback=_fake_refresh,
    )

    assert payload["status"] == "partial"
    assert payload["counts"] == {"published": 1, "blocked": 1, "unsupported": 0}
    assert {item["status"] for item in payload["results"]} == {"blocked", "published"}
    assert Path(payload["artifact_paths"]["ledger_json"]).is_file()


def test_detector_refresh_rolls_back_partial_publication(tmp_path: Path) -> None:
    repo = tmp_path / "app"
    _init_repo(repo)

    payload = fleet_detector_refresh_payload(
        projects_root=tmp_path,
        repository_paths=[repo],
        output_dir=tmp_path / "artifacts",
        as_of="2026-08-14T04:47:00Z",
        refresh_callback=_fake_refresh_with_invalid_run,
    )

    assert payload["status"] == "partial"
    assert payload["counts"] == {"published": 0, "blocked": 1, "unsupported": 0}
    assert "publication failed" in payload["results"][0]["reason"]
    published_root = repo / ".quality-runner" / "runs"
    assert not published_root.exists() or not any(published_root.iterdir())


def test_detector_refresh_retains_phase_diagnostics_when_expected_run_is_missing(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "app"
    _init_repo(repo)

    payload = fleet_detector_refresh_payload(
        projects_root=tmp_path,
        repository_paths=[repo],
        output_dir=tmp_path / "artifacts",
        as_of="2026-08-14T04:47:30Z",
        refresh_callback=_fake_refresh_with_missing_run,
    )

    result = payload["results"][0]
    assert result["status"] == "blocked"
    assert result["refresh_status"] == "blocked"
    assert result["refresh_diagnostics"]["missing_run_ids"] == [
        result["refresh_diagnostics"]["phases"]["run"]["run_id"]
    ]
    assert result["refresh_diagnostics"]["phases"]["run"] == {
        "run_id": result["refresh_diagnostics"]["missing_run_ids"][0],
        "status": "blocked",
        "reason": "refresh run phase exceeded the repository deadline",
        "timeout_scope": "repository",
        "timeout_seconds": 600,
        "timing_status": "timed-out",
    }
    assert "run phase blocked" in result["reason"]
    published_root = repo / ".quality-runner" / "runs"
    assert not published_root.exists() or not any(published_root.iterdir())


def test_detector_refresh_rejects_nonpositive_timeout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        fleet_detector_refresh_payload(projects_root=tmp_path, timeout_seconds=0)


def test_cli_help_names_exact_target_publication() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "fleet", "detector", "refresh", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "full skill-pack scans" in result.stdout
    assert "--target-override" in result.stdout
    assert "--target-path-override" in result.stdout
    assert "--agent-review-mode" in result.stdout


def test_public_pronto_contract_fixture_covers_each_repository_status() -> None:
    fixture = json.loads(
        (
            ROOT / "fixtures" / "contracts" / "public-adapters" / "pronto-detector-refresh.json"
        ).read_text(encoding="utf-8")
    )

    assert fixture["schema"] == "quality-runner-fleet-detector-refresh/v1"
    assert fixture["counts"] == {"published": 1, "blocked": 1, "unsupported": 1}
    assert {result["status"] for result in fixture["results"]} == {
        "published",
        "blocked",
        "unsupported",
    }
