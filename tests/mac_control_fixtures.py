from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

from quality_runner.fleet.contracts import digest
from quality_runner.fleet.mac_control import MAC_CONTROL_MANIFEST_SCHEMA
from quality_runner.fleet.mac_control_contracts import semantic_source_paths


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _repo(root: Path) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-b", "dev")
    _git(root, "config", "user.email", "mac-control@example.com")
    _git(root, "config", "user.name", "Mac Control Tests")
    (root / "README.md").write_text("# fixture\n", encoding="utf-8")
    source = root / "src" / "FixtureUI.swift"
    source.parent.mkdir()
    source.write_text(
        "\n".join(
            [
                "stable_identity fixture.settings AXIdentifier exactly_one",
                "correct_semantics AXButton Settings AXPress",
                "observable_state AXEnabled permission_unavailable",
                "useful_hierarchy FixtureWindow SettingsPanel exactly_one",
                "efficient_navigation direct_semantic fixture.settings",
                "verifiable_outcomes settings_state equals settings_visible",
                "route_flexibility mac_control fresh_state_handoff computer_use",
                "stable_change_behavior loading modal disabled permission_unavailable fail_closed",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")


def _write_manifest(repo: Path, manifest: dict[str, object]) -> None:
    manifest_dir = repo / ".mac-control"
    manifest_dir.mkdir(exist_ok=True)
    manifest_dir.joinpath("ideal-state.json").write_text(json.dumps(manifest), encoding="utf-8")
    _git(repo, "add", ".mac-control/ideal-state.json")
    _git(repo, "commit", "-m", "add Mac Control contract")


def _manifest(repo_id: str) -> dict[str, object]:
    return {
        "schema": "mac-control-task-manifest/v1",
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


def _manifest_v2(repo_id: str) -> dict[str, object]:
    manifest = _manifest(repo_id)
    manifest["schema"] = "mac-control-task-manifest/v2"
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    task["observable_states"] = ["enabled", "visible", "completed"]
    task["state_exemptions"] = {
        "focused": "Opening the panel does not retain focus on the trigger.",
        "selected": "The trigger is not selectable.",
        "expanded": "The panel is not expandable.",
        "loading": "The task completes synchronously.",
    }
    task["change_states"] = ["loading", "disabled"]
    task["change_state_exemptions"] = {
        "modal": "The task does not present a modal.",
        "permission_unavailable": "The task has no protected permission.",
    }
    task["navigation_strategy"] = "sequential_tabbing"
    task.pop("eligible_routes")
    task.pop("selected_route")
    task["focus_policy"] = "foreground"
    task["foreground_postcondition"] = "target_foreground"
    task["fallback_policy"] = "fresh_state_handoff"
    task["verification_oracle"] = {
        "oracle_id": "fixture.settings.visible",
        "kind": "window_state",
        "expected_state": "settings_visible",
        "independent_readback": True,
    }
    task["route_candidates"] = [
        {
            "id": "native-accessibility",
            "provider": "mac_control",
            "method": "accessibility",
            "interaction_mode": "semantic",
        },
        {
            "id": "computer-use-pointer",
            "provider": "computer_use",
            "method": "pointer",
            "interaction_mode": "pointer",
        },
    ]
    return manifest


def _manifest_v3(repo_id: str) -> dict[str, object]:
    manifest = _manifest_v2(repo_id)
    manifest["schema"] = "mac-control-task-manifest/v3"
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    cast(list[dict[str, object]], task["route_candidates"]).append(
        {
            "id": "verified-shortcut",
            "provider": "mac_control",
            "method": "shortcut",
            "interaction_mode": "keyboard",
        }
    )
    task["shortcut_acceleration"] = {
        "disposition": "built_in_verified",
        "command_id": "fixture.open-settings",
        "chord": "cmd+,",
        "conflict_policy": "app_managed",
        "contextual_availability": True,
    }
    return manifest


def _manifest_v4(repo_id: str) -> dict[str, object]:
    manifest = _manifest_v3(repo_id)
    manifest["schema"] = MAC_CONTROL_MANIFEST_SCHEMA
    manifest["criteria"] = {}
    task = cast(list[dict[str, object]], manifest["tasks"])[0]
    task["surface_kind"] = "native_app_ui"
    task["navigation_strategy"] = "direct_semantic"
    claims: dict[str, dict[str, str]] = {
        "stable_identity": {
            "selector_kind": "ax_identifier",
            "selector_value": "fixture.settings",
            "scope": "FixtureWindow",
            "uniqueness": "exactly_one",
        },
        "correct_semantics": {
            "role": "AXButton",
            "accessible_name": "Settings",
            "action": "AXPress",
        },
        "observable_state": {
            "property": "AXEnabled",
            "unavailable_behavior": "permission_unavailable",
        },
        "useful_hierarchy": {
            "container": "FixtureWindow",
            "relationship": "SettingsPanel",
            "uniqueness": "exactly_one",
        },
        "efficient_navigation": {
            "strategy": "direct_semantic",
            "entry_point": "fixture.settings",
        },
        "verifiable_outcomes": {
            "readback_provider": "mac_control",
            "property": "settings_state",
            "operator": "equals",
            "expected": "settings_visible",
        },
        "route_flexibility": {
            "primary_provider": "mac_control",
            "secondary_provider": "computer_use",
            "fallback_policy": "fresh_state_handoff",
        },
        "stable_change_behavior": {
            "scenarios": "loading,modal,disabled,permission_unavailable",
            "failure_behavior": "fail_closed",
        },
    }
    evidence_tokens = {
        "stable_identity": ["fixture.settings", "AXIdentifier", "exactly_one"],
        "correct_semantics": ["AXButton", "Settings", "AXPress"],
        "observable_state": ["AXEnabled", "permission_unavailable"],
        "useful_hierarchy": ["FixtureWindow", "SettingsPanel", "exactly_one"],
        "efficient_navigation": ["direct_semantic", "fixture.settings"],
        "verifiable_outcomes": ["settings_state", "equals", "settings_visible"],
        "route_flexibility": ["mac_control", "fresh_state_handoff", "computer_use"],
        "stable_change_behavior": [
            "loading",
            "modal",
            "disabled",
            "permission_unavailable",
            "fail_closed",
        ],
    }
    task["semantic_evidence"] = {
        criterion: {
            "level": "source_grounded",
            "claims": claim,
            "source_refs": [
                {
                    "path": "src/FixtureUI.swift",
                    "anchor": criterion,
                    "evidence_tokens": evidence_tokens[criterion],
                }
            ],
        }
        for criterion, claim in claims.items()
    }
    return manifest


def _source_digest(repo: Path, manifest: dict[str, object]) -> str:
    snapshots = [
        {
            "path": relative_path,
            "digest": digest((repo / relative_path).read_text(encoding="utf-8")),
        }
        for relative_path in semantic_source_paths(manifest)
    ]
    return digest(snapshots)


def _attempt(
    *,
    attempt_id: str,
    route: str = "native-accessibility",
    execution_result: str = "succeeded",
    verification_result: str = "passed",
    observed_state: str = "settings_visible",
    passed: bool = True,
) -> dict[str, object]:
    provider = "mac_control" if route == "native-accessibility" else "computer_use"
    method = "accessibility" if route == "native-accessibility" else "pointer"
    return {
        "attempt_id": attempt_id,
        "selected_route": route,
        "started_at": "2026-08-08T11:59:58+00:00",
        "completed_at": "2026-08-08T12:00:00+00:00",
        "execution_result": execution_result,
        "verification_result": verification_result,
        "receipt": {
            "receipt_id": f"fixture.{attempt_id}",
            "schema": "mac-control-operation-receipt/v3",
            "provider": provider,
            "method": method,
            "sha256": "a" * 64,
        },
        "postcondition": {
            "oracle_id": "fixture.settings.visible",
            "kind": "window_state",
            "expected_state": "settings_visible",
            "observed_state": observed_state,
            "operator": "equals",
            "passed": passed,
            "readback_provider": "mac_control",
        },
    }


def _evidence_v2(
    repo: Path,
    record: dict[str, object],
    manifest: dict[str, object],
    attempts: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema": "mac-control-task-evidence/v2",
        "repository_id": record["repo_id"],
        "observed_at": "2026-08-08T12:00:00+00:00",
        "observed_commit": _git(repo, "rev-parse", "HEAD"),
        "observed_source_digest": _source_digest(repo, manifest),
        "producer": {
            "id": "macctl-fixture",
            "kind": "mac_control",
            "version": "1.0.0",
        },
        "tasks": [{"task_id": "open-settings", "attempts": attempts}],
    }


def test_manifest_fixture_is_source_grounded() -> None:
    manifest = _manifest_v4("fixture")

    assert manifest["schema"] == MAC_CONTROL_MANIFEST_SCHEMA
    assert manifest["criteria"] == {}
