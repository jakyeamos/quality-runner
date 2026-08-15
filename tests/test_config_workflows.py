from __future__ import annotations

import json
from importlib import resources


def test_detect_capabilities_handles_file_sources_and_inactive_exceptions(tmp_path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"pre-cr": "pre-cr run"}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["pre_cr", "tests", "not_real"]',
                "",
                "[[quality_runner.accepted_exceptions]]",
                'capability = "tests"',
                'reason = "Expired exception should not suppress missing tests."',
                'owner = "qa"',
                'expires = "2000-01-01"',
                "",
                "[[quality_runner.accepted_exceptions]]",
                'capability = "tests"',
                'reason = "Invalid expiry should not suppress missing tests."',
                'owner = "qa"',
                'expires = "not-a-date"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="config-002")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert capability_map["available"] == [
        {
            "id": "pre_cr",
            "type": "command",
            "capability_kind": "local_command",
            "source": "package.json:scripts.pre-cr",
            "command": "pre-cr run",
            "language": "javascript",
            "required_by": "config",
            "verification_state": {
                "discovery": "command-discovered",
                "execution": "not-run",
                "result": "unknown",
            },
        },
    ]
    assert capability_map["missing"] == [
        {
            "id": "tests",
            "type": "command",
            "reason": "no quality command found for tests",
            "language": "javascript",
            "required_by": "config",
        }
    ]
    assert capability_map["accepted_exceptions"] == []


def test_detect_capabilities_treats_unknown_required_capabilities_as_noops(tmp_path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["not_real"]\n',
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="config-003")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert capability_map["available"] == []
    assert capability_map["missing"] == []
    assert capability_map["accepted_exceptions"] == []


def test_workflow_uses_config_default_profile_when_profile_is_omitted(tmp_path) -> None:
    from quality_runner.workflow import inspect_payload

    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\ndefault_profile = "default"\n',
        encoding="utf-8",
    )

    payload = inspect_payload(repo_root=tmp_path, run_id="config-profile")
    standards = json.loads(
        (tmp_path / ".quality-runner" / "runs" / "config-profile" / "standards.json").read_text()
    )

    assert payload["schema"] == "quality-runner-inspect-result-v0.1"
    assert standards["profile"] == "default"
    assert {"type": "config", "path": ".quality-runner.toml"} in standards["sources"]


def test_custom_profile_can_be_selected_from_repo_config(tmp_path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "bun@1.2.0",
                "scripts": {"lint": "eslint ."},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'default_profile = "team"',
                "",
                "[quality_runner.profiles.team]",
                'extends = "default"',
                'required_capabilities = ["lint", "tests"]',
                'allowed_package_managers = ["bun"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="custom-profile")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="team")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert packet["profile"] == "team"
    assert packet["profile_config"] == {
        "extends": "default",
        "required_capabilities": ["lint", "tests"],
        "required_capabilities_configured": True,
        "allowed_package_managers": ["bun"],
    }
    assert "package_manager_mismatch" not in {
        requirement["id"] for requirement in packet["requirements"]
    }
    assert capability_map["missing"] == [
        {
            "id": "tests",
            "type": "command",
            "reason": "no quality command found for tests",
            "language": "javascript",
            "required_by": "profile",
        }
    ]


def test_workflow_allows_explicit_profile_to_override_config_default(tmp_path) -> None:
    from quality_runner.workflow import run_payload

    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\ndefault_profile = "someone-else"\nrequired_capabilities = []\n',
        encoding="utf-8",
    )

    payload = run_payload(repo_root=tmp_path, run_id="config-run", profile="default")
    standards = json.loads(
        (tmp_path / ".quality-runner" / "runs" / "config-run" / "standards.json").read_text()
    )

    assert payload["status"] == "clean"
    assert standards["profile"] == "default"


def test_packaged_schema_files_are_parseable() -> None:
    schema_root = resources.files("quality_runner").joinpath("schemas")
    schema_names = {
        "repo-scan.schema.json",
        "standards.schema.json",
        "capability-matrix.schema.json",
        "package-manager-preflight.schema.json",
        "gate-verification.schema.json",
        "gate-verification-v0.2.schema.json",
        "quality-audit.schema.json",
        "remediation-plan.schema.json",
        "agent-handoff.schema.json",
        "controller-report-validation.schema.json",
        "run-manifest.schema.json",
        "run-result.schema.json",
        "run-summary.schema.json",
        "intent.schema.json",
        "gate-run.schema.json",
        "gate-response.schema.json",
        "fix-proposals.schema.json",
        "review-context.schema.json",
        "review-adapter-response.schema.json",
        "review-manifest.schema.json",
        "review-delta.schema.json",
        "plan-config.schema.json",
        "roadmap.schema.json",
        "planning-state.schema.json",
        "phase-plan.schema.json",
        "phase-batch-result.schema.json",
        "phase-verification.schema.json",
        "outcome.schema.json",
        "performance.schema.json",
        "delivery-contract.schema.json",
        "delivery-result.schema.json",
    }

    loaded = {}
    for name in schema_names:
        payload = json.loads(schema_root.joinpath(name).read_text(encoding="utf-8"))
        loaded[name] = payload

    assert set(loaded) == schema_names
    assert all(
        payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        for payload in loaded.values()
    )
    assert all(payload["type"] == "object" for payload in loaded.values())


def test_artifact_schema_additions_remain_optional_and_agent_handoff_versioned() -> None:
    schema_root = resources.files("quality_runner").joinpath("schemas")
    repo_scan = json.loads(schema_root.joinpath("repo-scan.schema.json").read_text())
    capability_matrix = json.loads(
        schema_root.joinpath("capability-matrix.schema.json").read_text()
    )
    remediation_plan = json.loads(schema_root.joinpath("remediation-plan.schema.json").read_text())
    agent_handoff = json.loads(schema_root.joinpath("agent-handoff.schema.json").read_text())

    assert repo_scan["properties"]["schema"]["const"] == "quality-runner-repo-scan-v0.1"
    assert "workspaces" not in repo_scan["required"]
    assert "scan_exclusions" not in repo_scan["required"]
    assert "repo_surfaces" not in repo_scan["required"]
    assert "ecosystems" not in repo_scan["required"]
    assert "ci_checks" not in repo_scan["required"]
    assert "generated_code" not in repo_scan["required"]
    assert capability_matrix["properties"]["schema"]["const"] == (
        "quality-runner-capability-map-v0.1"
    )
    capability_properties = capability_matrix["$defs"]["capability"]["properties"]
    assert {
        "required_by",
        "owner",
        "severity",
        "capability_kind",
        "local_execution",
        "ci_status",
        "verification_state",
    }.issubset(capability_properties)
    assert (
        "local-executed"
        in capability_matrix["$defs"]["verificationState"]["properties"]["execution"]["enum"]
    )
    assert remediation_plan["properties"]["schema"]["const"] == (
        "quality-runner-remediation-plan-v0.1"
    )
    assert "adoption_stage" not in remediation_plan["required"]
    assert "stopping_criteria" not in remediation_plan["required"]
    assert agent_handoff["properties"]["schema"]["const"] == "quality-runner-agent-handoff-v0.2"
    assert "gates-discovered" in agent_handoff["properties"]["status"]["enum"]
    assert "gates-executed" in agent_handoff["properties"]["status"]["enum"]
    assert "gates-blocked" in agent_handoff["properties"]["status"]["enum"]
    assert "gates-failed" in agent_handoff["properties"]["status"]["enum"]
    assert "gates-clean" in agent_handoff["properties"]["status"]["enum"]
    assert agent_handoff["properties"]["next_slice"]["oneOf"] == [
        {"type": "null"},
        {"$ref": "#/$defs/remediationSlice"},
    ]
    action_group = agent_handoff["$defs"]["actionGroup"]
    assert action_group["required"] == ["class", "actions"]
    assert action_group["anyOf"] == [{"required": ["gate_ids"]}, {"required": ["finding_ids"]}]
    assert remediation_plan["$defs"]["slice"]["properties"]["action_groups"]["items"]["$ref"] == (
        "#/$defs/actionGroup"
    )
    assert (
        agent_handoff["$defs"]["remediationSlice"]["properties"]["action_groups"]["items"]["$ref"]
        == "#/$defs/actionGroup"
    )
    assert "adoption_stage" not in agent_handoff["required"]
    assert "stopping_criteria" not in agent_handoff["required"]
