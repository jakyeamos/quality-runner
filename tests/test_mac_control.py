from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from mac_control_fixtures import (
    _attempt,
    _evidence_v2,
    _git,
    _manifest,
    _manifest_v2,
    _manifest_v3,
    _manifest_v4,
    _repo,
    _write_manifest,
)

from quality_runner.cli import main
from quality_runner.fleet.discovery import repository_record_for_root
from quality_runner.fleet.mac_control import (
    mac_control_audit_payload,
    mac_control_feed_payload,
    mac_control_replay_payload,
    mac_control_report_payload,
    validate_manifest,
)
from quality_runner.fleet.mac_control_artifacts import build_summary
from quality_runner.fleet.mac_control_contracts import MacControlAuditError


def test_manifest_separates_static_contract_from_live_task_evidence(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    _write_manifest(repo, _manifest_v4(str(record["repo_id"])))

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


def test_legacy_manifest_does_not_earn_current_static_score(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    _write_manifest(repo, _manifest(str(record["repo_id"])))

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        as_of="2026-08-08T12:00:00+00:00",
    )
    entry = result["report"]["repositories"][0]

    assert entry["manifest_schema"] == "mac-control-task-manifest/v1"
    assert entry["implementation_contract"]["status"] == "review_required"
    assert entry["implementation_contract"]["criteria_passed_count"] == 0
    assert entry["implementation_contract"]["criteria_total"] == 8
    assert result["summary"]["implementation_status"] == "review_required"
    assert result["summary"]["implementation_criteria_passed_count"] == 0
    assert result["summary"]["implementation_criteria_total"] == 8

    stale_entry = {
        **entry,
        "manifest_schema": "mac-control-task-manifest/v1",
        "implementation_contract": {
            **entry["implementation_contract"],
            "status": "passed",
            "criteria_passed_count": 8,
        },
    }
    stale_summary = build_summary(
        audit_id="stale-fixture",
        observed_at="2026-08-08T12:00:00+00:00",
        projects_root=projects,
        repositories=[stale_entry],
        live=False,
    )
    assert stale_summary["implementation_status"] == "review_required"
    assert stale_summary["implementation_criteria_passed_count"] == 0
    assert stale_summary["implementation_criteria_total"] == 8


def test_evidence_sidecar_publishes_companion_report_without_changing_qr_score(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    manifest = _manifest_v4(str(record["repo_id"]))
    _write_manifest(repo, manifest)
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence_dir.joinpath(f"{record['repo_id']}.json").write_text(
        json.dumps(
            _evidence_v2(
                repo,
                record,
                manifest,
                [_attempt(attempt_id=f"open-settings-{index}") for index in range(1, 4)],
            )
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


def test_dirty_grounded_source_is_not_attributed_to_the_head_commit(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    _write_manifest(repo, _manifest_v4(str(record["repo_id"])))
    source = repo / "src" / "FixtureUI.swift"
    source.write_text(source.read_text(encoding="utf-8") + "// local edit\n", encoding="utf-8")

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        as_of="2026-08-08T12:00:00+00:00",
    )
    entry = result["report"]["repositories"][0]

    assert entry["source_provenance"]["status"] == "dirty"
    assert entry["source_provenance"]["dirty_paths"] == ["src/FixtureUI.swift"]
    assert entry["implementation_contract"]["status"] == "review_required"
    assert any(
        "source provenance is dirty" in error
        for error in entry["implementation_contract"]["grounding_errors"]
    )


def test_structured_evidence_rejects_route_and_source_provenance_mismatch(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    manifest = _manifest_v4(str(record["repo_id"]))
    _write_manifest(repo, manifest)
    sidecar = _evidence_v2(
        repo,
        record,
        manifest,
        [_attempt(attempt_id="open-settings-1", route="not-declared")],
    )
    sidecar["observed_source_digest"] = "b" * 64
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence_dir.joinpath(f"{record['repo_id']}.json").write_text(
        json.dumps(sidecar), encoding="utf-8"
    )

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        evidence_dir=evidence_dir,
        as_of="2026-08-08T12:00:00+00:00",
    )
    live = result["report"]["repositories"][0]["live_task_evidence"]

    assert live["status"] == "blocked"
    assert live["measured_task_count"] == 0
    assert any("observed_source_digest" in reason for reason in live["failure_reasons"])
    assert any("selected_route" in reason for reason in live["failure_reasons"])


def test_manifest_rejects_guessing_routes_and_incomplete_state() -> None:
    manifest = _manifest("repo")
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    task["navigation_strategy"] = "sequential_tabbing"
    task["observable_states"] = ["enabled"]
    assert any("sequential tabbing" in error for error in validate_manifest(manifest))
    assert any(
        "observable_states is missing completed" in error for error in validate_manifest(manifest)
    )


def test_v4_rejects_self_attested_criteria_and_surface_provider_mismatch() -> None:
    manifest = _manifest_v4("repo")
    legacy_criteria = cast(dict[str, bool], _manifest("repo")["criteria"])
    manifest["criteria"] = {criterion: True for criterion in legacy_criteria}
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    task["surface_kind"] = "web_content"

    errors = validate_manifest(manifest)

    assert any("criteria must be empty" in error for error in errors)
    assert any("web_content requires a browser_connector" in error for error in errors)
    assert any("must not claim a native Mac Control route" in error for error in errors)


def test_v4_accepts_aria_label_as_dom_native_web_identity() -> None:
    manifest = _manifest_v4("repo")
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    task["surface_kind"] = "web_content"
    task["stable_target_id"] = "Settings"
    task["route_candidates"] = [
        {
            "id": "browser-dom",
            "provider": "browser_connector",
            "method": "adapter",
            "interaction_mode": "semantic",
        },
        {
            "id": "computer-use-pointer",
            "provider": "computer_use",
            "method": "pointer",
            "interaction_mode": "pointer",
        },
    ]
    semantic_evidence = cast(dict[str, dict[str, object]], task["semantic_evidence"])
    stable_claims = cast(dict[str, str], semantic_evidence["stable_identity"]["claims"])
    stable_claims["selector_kind"] = "aria_label"
    stable_claims["selector_value"] = "Settings"
    navigation_claims = cast(dict[str, str], semantic_evidence["efficient_navigation"]["claims"])
    navigation_claims["entry_point"] = "Settings"
    outcome_claims = cast(dict[str, str], semantic_evidence["verifiable_outcomes"]["claims"])
    outcome_claims["readback_provider"] = "browser_connector"
    route_claims = cast(dict[str, str], semantic_evidence["route_flexibility"]["claims"])
    route_claims["primary_provider"] = "browser_connector"

    assert validate_manifest(manifest) == []


def test_v4_missing_source_token_is_descriptive_and_non_scoring(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    source = repo / "src" / "FixtureUI.swift"
    source.write_text(
        source.read_text(encoding="utf-8").replace("AXIdentifier", "missing-identifier"),
        encoding="utf-8",
    )
    _write_manifest(repo, _manifest_v4(str(record["repo_id"])))

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        as_of="2026-08-08T12:00:00+00:00",
    )
    implementation = result["report"]["repositories"][0]["implementation_contract"]

    assert implementation["status"] == "review_required"
    assert implementation["criteria_passed_count"] == 7
    assert implementation["dimension_states"]["stable_identity"]["status"] == (
        "not_source_grounded"
    )
    assert any("AXIdentifier" in error for error in implementation["grounding_errors"])


def test_v4_symlinked_source_is_descriptive_and_non_scoring(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    source = repo / "src" / "FixtureUI.swift"
    target = repo / "src" / "FixtureUITarget.swift"
    source.rename(target)
    source.symlink_to(target.name)
    _write_manifest(repo, _manifest_v4(str(record["repo_id"])))

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        as_of="2026-08-08T12:00:00+00:00",
    )
    implementation = result["report"]["repositories"][0]["implementation_contract"]

    assert implementation["status"] == "review_required"
    assert implementation["criteria_passed_count"] == 0
    assert any("must not be a symlink" in error for error in implementation["grounding_errors"])


def test_v4_source_anchor_must_be_unique_and_locally_grounded(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    source = repo / "src" / "FixtureUI.swift"
    source.write_text(
        source.read_text(encoding="utf-8") + "\nstable_identity unrelated_duplicate\n",
        encoding="utf-8",
    )
    _write_manifest(repo, _manifest_v4(str(record["repo_id"])))

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        as_of="2026-08-08T12:00:00+00:00",
    )
    implementation = result["report"]["repositories"][0]["implementation_contract"]

    assert implementation["status"] == "review_required"
    assert implementation["criteria_passed_count"] == 7
    assert any("anchor is not unique" in error for error in implementation["grounding_errors"])


def test_v4_rejects_generic_oracle_and_cloned_dimension_evidence() -> None:
    manifest = _manifest_v4("repo")
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    oracle = cast(dict[str, object], task["verification_oracle"])
    oracle["expected_state"] = "visible"
    semantic_evidence = cast(dict[str, object], task["semantic_evidence"])
    semantic_evidence["correct_semantics"] = json.loads(
        json.dumps(semantic_evidence["stable_identity"])
    )

    errors = validate_manifest(manifest)

    assert any("machine-checkable value" in error for error in errors)
    assert any("criterion-specific, not cloned" in error for error in errors)


def test_v4_rejects_cross_field_spoofing_and_nonimplementation_refs() -> None:
    manifest = _manifest_v4("repo")
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    task["navigation_strategy"] = "shortcut"
    semantic_evidence = cast(dict[str, dict[str, object]], task["semantic_evidence"])
    outcome_claims = cast(dict[str, str], semantic_evidence["verifiable_outcomes"]["claims"])
    outcome_claims["expected"] = "different_state"
    outcome_claims["readback_provider"] = "caller"
    route_claims = cast(dict[str, str], semantic_evidence["route_flexibility"]["claims"])
    route_claims["secondary_provider"] = "mac_control"
    change_claims = cast(dict[str, str], semantic_evidence["stable_change_behavior"]["claims"])
    change_claims["failure_behavior"] = "ignore_and_continue"
    stable_refs = cast(list[dict[str, object]], semantic_evidence["stable_identity"]["source_refs"])
    stable_refs[0]["path"] = "docs/mac-control.md"

    errors = validate_manifest(manifest)

    assert any("strategy must match task navigation_strategy" in error for error in errors)
    assert any(
        "expected must match verification_oracle.expected_state" in error for error in errors
    )
    assert any("readback_provider must match a route candidate" in error for error in errors)
    assert any("secondary_provider must differ" in error for error in errors)
    assert any("failure_behavior is unsupported" in error for error in errors)
    assert any("must reference implementation source" in error for error in errors)
    assert any("implementation-source extension" in error for error in errors)


def test_v3_manifest_is_readable_but_declaration_only(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    manifest = _manifest_v3(str(record["repo_id"]))
    assert validate_manifest(manifest) == []
    _write_manifest(repo, manifest)

    result = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "audit",
        as_of="2026-08-08T12:00:00+00:00",
    )
    entry = result["report"]["repositories"][0]
    task = entry["supported_tasks"][0]

    assert entry["manifest_schema"] == "mac-control-task-manifest/v3"
    assert task["selected_route"] == ""
    assert task["route_candidates"][1]["provider"] == "computer_use"
    assert task["shortcut_acceleration"]["disposition"] == "built_in_verified"
    assert entry["implementation_contract"]["status"] == "review_required"
    assert entry["implementation_contract"]["criteria_passed_count"] == 0
    assert entry["implementation_contract"]["declaration_criteria_count"] == 8
    assert entry["implementation_contract"]["evidence_level"] == "declaration_only"
    assert entry["live_task_evidence"]["status"] == "review_required"

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
                        "selected_route": "computer-use-pointer",
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
    measured = mac_control_audit_payload(
        projects_root=projects,
        output_dir=tmp_path / "measured-audit",
        evidence_dir=evidence_dir,
        as_of="2026-08-08T12:00:00+00:00",
    )

    assert measured["report"]["repositories"][0]["supported_tasks"][0]["selected_route"] == (
        "computer-use-pointer"
    )
    live = measured["report"]["repositories"][0]["live_task_evidence"]
    assert live["status"] == "blocked"
    assert any("cannot satisfy live measurement" in reason for reason in live["failure_reasons"])


def test_v2_manifest_requires_state_accounting_and_rejects_static_selection() -> None:
    manifest = _manifest_v2("repo")
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    cast(dict[str, str], task["state_exemptions"]).pop("focused")
    task["selected_route"] = "accessibility"
    errors = validate_manifest(manifest)

    assert any("selected_route is runtime evidence" in error for error in errors)
    assert any("must declare or exempt focused" in error for error in errors)


def test_v3_manifest_rejects_unverifiable_custom_shortcut_surface() -> None:
    manifest = _manifest_v3("repo")
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    task["shortcut_acceleration"] = {
        "disposition": "customizable_verified",
        "command_id": "fixture.open-settings",
        "customization_surface": "macos_app_shortcut",
        "conflict_policy": "detect_before_assignment",
        "contextual_availability": False,
        "reversible_assignment": False,
    }
    errors = validate_manifest(manifest)

    assert any("contextual_availability true" in error for error in errors)
    assert any("exact menu_path" in error for error in errors)
    assert any("reversible_assignment true" in error for error in errors)


def test_invalid_not_applicable_manifest_is_review_required(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    manifest = _manifest("repo")
    manifest["applicability"] = "not_applicable"
    _write_manifest(repo, manifest)

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
    _write_manifest(repo, _manifest_v4(str(record["repo_id"])))
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
    manifest = _manifest_v4(str(record["repo_id"]))
    _write_manifest(repo, manifest)
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    evidence_dir.joinpath(f"{record['repo_id']}.json").write_text(
        json.dumps(
            _evidence_v2(
                repo,
                record,
                manifest,
                [
                    _attempt(attempt_id="open-settings-1"),
                    _attempt(attempt_id="open-settings-2"),
                    _attempt(
                        attempt_id="open-settings-3",
                        execution_result="failed",
                        verification_result="failed",
                        observed_state="settings_hidden",
                        passed=False,
                    ),
                ],
            )
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
    _write_manifest(repo, _manifest_v4(str(record["repo_id"])))
    manifest_dir = repo / ".mac-control"

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


def test_mac_control_fleet_cli_audits_v4_manifest_in_fresh_process(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    _write_manifest(repo, _manifest_v4(str(record["repo_id"])))

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "fleet",
            "mac-control",
            "audit",
            "run",
            "--repo-path",
            str(repo),
            "--projects-root",
            str(projects),
            "--output-dir",
            str(tmp_path / "fresh-process-audit"),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["summary"]["implementation_criteria_passed_count"] == 8


def test_mac_control_fleet_cli_routes_run_replay_report_and_feed(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = projects / "fixture"
    _repo(repo)
    record = repository_record_for_root(repo)
    _write_manifest(repo, _manifest_v4(str(record["repo_id"])))
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
