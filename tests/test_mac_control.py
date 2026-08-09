from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from quality_runner.cli import main
from quality_runner.fleet.discovery import repository_record_for_root
from quality_runner.fleet.mac_control import (
    MAC_CONTROL_MANIFEST_SCHEMA,
    mac_control_audit_payload,
    mac_control_feed_payload,
    mac_control_replay_payload,
    mac_control_report_payload,
    validate_manifest,
)
from quality_runner.fleet.mac_control_contracts import MacControlAuditError


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _repo(root: Path) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "dev")
    _git(root, "config", "user.email", "mac-control@example.com")
    _git(root, "config", "user.name", "Mac Control Tests")
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")


def _manifest(repo_id: str) -> dict[str, object]:
    return {
        "schema": MAC_CONTROL_MANIFEST_SCHEMA,
        "repository_id": repo_id,
        "repository_name": "fixture",
        "applicability": "applicable",
        "applicability_reason": "The fixture exposes a supported desktop task.",
        "app": {"name": "Fixture App", "bundle_id": "com.example.fixture"},
        "criteria": {
            "stable_identity": True,
            "correct_semantics": True,
            "observable_state": True,
            "useful_hierarchy": True,
            "efficient_navigation": True,
            "verifiable_outcomes": True,
            "route_flexibility": True,
            "stable_change_behavior": True,
        },
        "tasks": [
            {
                "task_id": "open-settings",
                "stable_target_id": "fixture.settings",
                "hierarchy": "Fixture window > Settings panel",
                "semantic_action": "press settings button",
                "observable_postcondition": "Settings panel is visible and selected",
                "observable_states": [
                    "enabled",
                    "focused",
                    "selected",
                    "expanded",
                    "visible",
                    "loading",
                    "completed",
                ],
                "navigation_strategy": "semantic target lookup",
                "eligible_routes": ["accessibility", "keyboard"],
                "selected_route": "accessibility",
                "change_states": ["loading", "modal", "disabled", "permission_unavailable"],
                "accessibility": {
                    "identifier": "fixture.settings",
                    "role": "AXButton",
                    "required_actions": ["AXPress"],
                },
            }
        ],
    }


def test_manifest_separates_static_contract_from_live_task_evidence(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    manifest_dir = repo / ".mac-control"
    manifest_dir.mkdir()
    manifest_dir.joinpath("ideal-state.json").write_text(
        json.dumps(_manifest(str(record["repo_id"]))), encoding="utf-8"
    )

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        as_of="2026-08-08T12:00:00+00:00",
    )
    entry = result["report"]["repositories"][0]

    assert entry["applicability"] == "applicable"
    assert entry["supported_tasks"][0]["attempts"] == 0
    assert entry["implementation_contract"]["status"] == "passed"
    assert entry["implementation_contract"]["criteria_passed_count"] == 8
    assert entry["live_task_evidence"]["status"] == "review_required"
    assert entry["live_task_evidence"]["measured_task_count"] == 0
    assert result["summary"]["implementation_status"] == "passed"
    assert result["summary"]["implementation_criteria_passed_count"] == 8
    assert result["summary"]["live_status"] == "review_required"
    assert result["summary"]["status"] == "review_required"
    assert (
        mac_control_replay_payload(output_dir=Path(result["artifact_root"]))["status"] == "passed"
    )
    report = mac_control_report_payload(output_dir=Path(result["artifact_root"]))
    assert report["status"] == "review_required"
    assert Path(report["artifact_paths"]["report_json"]).is_file()

    missing = tmp_path / "missing-projects"
    missing_repo = missing / "missing"
    _repo(missing_repo)
    missing_result = mac_control_audit_payload(
        projects_root=missing,
        output_dir=tmp_path / "missing-audit",
        as_of="2026-08-08T12:00:00+00:00",
    )
    missing_entry = missing_result["report"]["repositories"][0]
    assert missing_entry["applicability"] == "unknown"
    assert missing_entry["implementation_contract"]["status"] == "blocked"
    assert missing_entry["live_task_evidence"]["status"] == "blocked"
    assert "No repository-owned Mac Control manifest" in missing_entry["applicability_reason"]
    assert missing_entry["repository_id"] in missing_result["summary"]["failing_repository_ids"]


def test_evidence_sidecar_publishes_companion_report_without_changing_qr_score(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    manifest_dir = repo / ".mac-control"
    manifest_dir.mkdir()
    manifest_dir.joinpath("ideal-state.json").write_text(
        json.dumps(_manifest(str(record["repo_id"]))), encoding="utf-8"
    )
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence_dir.joinpath(f"{record['repo_id']}.json").write_text(
        json.dumps(
            {
                "schema": "mac-control-task-evidence/v1",
                "repository_id": record["repo_id"],
                "observed_at": "2026-08-08T12:00:00+00:00",
                "observed_commit": _git(repo, "rev-parse", "HEAD"),
                "criteria": {"stable_identity": True},
                "tasks": [
                    {
                        "task_id": "open-settings",
                        "attempts": 3,
                        "successes": 3,
                        "evidence": ["receipt:fixture.open-settings"],
                    }
                ],
                "evidence": ["receipt:fixture.open-settings"],
            }
        ),
        encoding="utf-8",
    )

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        evidence_dir=evidence_dir,
        as_of="2026-08-08T12:00:00+00:00",
    )
    entry = result["report"]["repositories"][0]
    assert entry["supported_tasks"][0]["attempts"] == 3
    assert entry["supported_tasks"][0]["successes"] == 3
    assert entry["implementation_contract"]["status"] == "passed"
    assert entry["live_task_evidence"]["status"] == "passed"
    assert result["summary"]["implementation_status"] == "passed"
    assert result["summary"]["live_status"] == "passed"
    assert result["summary"]["status"] == "passed"

    publication = mac_control_feed_payload(output_dir=Path(result["artifact_root"]))
    assert Path(publication["report_path"]).is_file()
    published = json.loads(Path(publication["report_path"]).read_text(encoding="utf-8"))
    assert published["schema_version"] == "pronto-mac-control-ideal-state/v1"
    assert published["scope"] == "quality_runner_fleet"


def test_manifest_rejects_guessing_routes_and_incomplete_state() -> None:
    manifest = _manifest("repo")
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    task["navigation_strategy"] = "sequential_tabbing"
    task["observable_states"] = ["enabled"]
    assert any("sequential tabbing" in error for error in validate_manifest(manifest))
    assert any(
        "observable_states is missing completed" in error for error in validate_manifest(manifest)
    )


def test_invalid_not_applicable_manifest_is_review_required(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    manifest_dir = repo / ".mac-control"
    manifest_dir.mkdir()
    manifest = _manifest("repo")
    manifest["applicability"] = "not_applicable"
    manifest_dir.joinpath("ideal-state.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        as_of="2026-08-08T12:00:00+00:00",
    )

    entry = result["report"]["repositories"][0]
    assert entry["validation_errors"]
    assert entry["implementation_contract"]["status"] == "failed"
    assert result["summary"]["status"] == "review_required"


def test_live_lane_records_redacted_provider_result(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    manifest_dir = repo / ".mac-control"
    manifest_dir.mkdir()
    manifest_dir.joinpath("ideal-state.json").write_text(
        json.dumps(_manifest(str(record["repo_id"]))), encoding="utf-8"
    )
    provider = tmp_path / "macctl-fixture"
    provider.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' \'{"status":"succeeded","result":{"structural_valid":true,"findings":[],"redacted":true}}\'\n',
        encoding="utf-8",
    )
    provider.chmod(provider.stat().st_mode | 0o111)
    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        live=True,
        macctl_path=str(provider),
        as_of="2026-08-08T12:00:00+00:00",
    )
    entry = result["report"]["repositories"][0]
    assert "macctl:ideal-state.audit:structural_pass" in entry["evidence"]
    assert entry["implementation_contract"]["status"] == "passed"
    assert entry["live_task_evidence"]["status"] == "review_required"
    assert result["summary"]["measured_task_count"] == 0


def test_live_task_failure_is_distinct_from_missing_measurement(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    manifest_dir = repo / ".mac-control"
    manifest_dir.mkdir()
    manifest_dir.joinpath("ideal-state.json").write_text(
        json.dumps(_manifest(str(record["repo_id"]))), encoding="utf-8"
    )
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence_dir.joinpath(f"{record['repo_id']}.json").write_text(
        json.dumps(
            {
                "schema": "mac-control-task-evidence/v1",
                "repository_id": record["repo_id"],
                "observed_at": "2026-08-08T12:00:00+00:00",
                "observed_commit": _git(repo, "rev-parse", "HEAD"),
                "tasks": [
                    {
                        "task_id": "open-settings",
                        "attempts": 3,
                        "successes": 2,
                        "evidence": ["receipt:fixture.open-settings"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        evidence_dir=evidence_dir,
        as_of="2026-08-08T12:00:00+00:00",
    )
    entry = result["report"]["repositories"][0]

    assert entry["implementation_contract"]["status"] == "passed"
    assert entry["live_task_evidence"]["status"] == "failed"
    assert result["summary"]["live_status"] == "failed"
    assert result["summary"]["status"] == "review_required"


def test_live_provider_failures_and_scope_boundaries_are_explicit(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    manifest_dir = repo / ".mac-control"
    manifest_dir.mkdir()
    manifest_dir.joinpath("ideal-state.json").write_text(
        json.dumps(_manifest(str(record["repo_id"]))), encoding="utf-8"
    )

    invalid_json_provider = tmp_path / "invalid-json"
    invalid_json_provider.write_text("#!/bin/sh\nprintf 'not-json\\n'\n", encoding="utf-8")
    invalid_json_provider.chmod(invalid_json_provider.stat().st_mode | 0o111)
    invalid = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "invalid-audit",
        live=True,
        macctl_path=str(invalid_json_provider),
        as_of="2026-08-08T12:00:00+00:00",
    )
    provider_path = Path(invalid["artifact_root"]) / "providers" / f"{record['repo_id']}.json"
    assert json.loads(provider_path.read_text(encoding="utf-8"))["status"] == "failed"
    assert invalid["report"]["repositories"][0]["live_task_evidence"]["status"] == "blocked"

    unavailable = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "unavailable-audit",
        live=True,
        macctl_path=str(tmp_path / "does-not-exist"),
        as_of="2026-08-08T12:00:00+00:00",
    )
    unavailable_provider = (
        Path(unavailable["artifact_root"]) / "providers" / f"{record['repo_id']}.json"
    )
    assert json.loads(unavailable_provider.read_text(encoding="utf-8"))["status"] == "unavailable"

    manifest_without_app = _manifest(str(record["repo_id"]))
    manifest_without_app.pop("app")
    manifest_dir.joinpath("ideal-state.json").write_text(
        json.dumps(manifest_without_app), encoding="utf-8"
    )
    blocked = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "blocked-audit",
        live=True,
        macctl_path="unused",
        as_of="2026-08-08T12:00:00+00:00",
    )
    blocked_provider = Path(blocked["artifact_root"]) / "providers" / f"{record['repo_id']}.json"
    assert json.loads(blocked_provider.read_text(encoding="utf-8"))["status"] == "blocked"

    with pytest.raises(MacControlAuditError, match="outside the bounded projects root"):
        mac_control_audit_payload(
            projects_root=projects,
            repository_paths=[tmp_path / "outside"],
            output_dir=tmp_path / "outside-audit",
        )


def test_mac_control_fleet_cli_routes_run_replay_report_and_feed(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    manifest_dir = repo / ".mac-control"
    manifest_dir.mkdir()
    manifest_dir.joinpath("ideal-state.json").write_text(
        json.dumps(_manifest(str(record["repo_id"]))), encoding="utf-8"
    )
    output = tmp_path / "audit"
    audit = mac_control_audit_payload(
        projects_root=projects,
        output_dir=output,
        as_of="2026-08-08T12:00:00+00:00",
    )
    artifact_root = Path(audit["artifact_root"])

    assert (
        main(
            [
                "fleet",
                "mac-control",
                "audit",
                "run",
                "--repo-path",
                str(repo),
                "--projects-root",
                str(projects),
                "--output-dir",
                str(tmp_path / "cli-run"),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "fleet",
                "mac-control",
                "audit",
                "replay",
                "--output-dir",
                str(artifact_root),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "fleet",
                "mac-control",
                "audit",
                "report",
                "--output-dir",
                str(artifact_root),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "fleet",
                "mac-control",
                "audit",
                "feed",
                "--output-dir",
                str(artifact_root),
                "--json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "fleet",
                "mac-control",
                "audit",
                "run",
                "--all",
                "--repo-path",
                str(repo),
                "--projects-root",
                str(projects),
                "--json",
            ]
        )
        == 1
    )
