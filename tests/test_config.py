from __future__ import annotations

import json
from importlib import resources


def test_load_repo_config_reads_default_profile_required_capabilities_and_exceptions(
    tmp_path,
) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'default_profile = "default"',
                'required_capabilities = ["lint", "tests"]',
                "",
                "[[quality_runner.accepted_exceptions]]",
                'capability = "truth_file"',
                'reason = "Fixture repo has no project truth file."',
                'owner = "platform"',
                'expires = "2999-01-01"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config == {
        "schema": "quality-runner-config-v0.1",
        "path": ".quality-runner.toml",
        "default_profile": "default",
        "profiles": {},
        "required_capabilities": ["lint", "tests"],
        "required_capabilities_configured": True,
        "allowed_package_managers": [],
        "scan_exclusions": [],
        "accepted_exceptions": [
            {
                "capability": "truth_file",
                "reason": "Fixture repo has no project truth file.",
                "owner": "platform",
                "expires": "2999-01-01",
            }
        ],
        "accepted_dispositions": [],
        "gates": [],
        "gate_timeouts": {},
        "severity_overrides": {},
        "structural_scan": {},
        "warnings": [],
    }


def test_load_repo_config_reads_gates_and_severity_overrides(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["lint", "tests"]',
                'allowed_package_managers = ["bun", "pnpm"]',
                "",
                "[quality_runner.severity_overrides]",
                'missing-tests = "critical"',
                'lint = "warning"',
                "",
                "[quality_runner.gate_timeouts]",
                "tests = 240",
                "pre_cr = 600",
                "",
                "[[quality_runner.gates]]",
                'id = "lint"',
                'command = "python -c \\"raise SystemExit(99)\\""',
                'ecosystem = "python"',
                'source = "local policy"',
                'owner = "platform"',
                "required = true",
                'severity = "blocker"',
                "",
                "[[quality_runner.accepted_exceptions]]",
                'capability = "tests"',
                'reason = "Temporarily delegated to integration suite."',
                'owner = "qa"',
                'expires = "2999-01-01"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["gates"] == [
        {
            "id": "lint",
            "command": 'python -c "raise SystemExit(99)"',
            "ecosystem": "python",
            "source": "local policy",
            "owner": "platform",
            "required": True,
            "severity": "blocker",
        }
    ]
    assert config["allowed_package_managers"] == ["bun", "pnpm"]
    assert config["scan_exclusions"] == []
    assert config["gate_timeouts"] == {"tests": 240, "pre_cr": 600}
    assert config["severity_overrides"] == {"missing-tests": "critical", "lint": "warning"}
    assert config["accepted_exceptions"] == [
        {
            "capability": "tests",
            "reason": "Temporarily delegated to integration suite.",
            "owner": "qa",
            "expires": "2999-01-01",
        }
    ]
    assert not (tmp_path / "should-not-exist").exists()


def test_load_repo_config_reads_artifact_privacy_and_retention_policy(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.artifacts]",
                'redact_patterns = ["(?i)secret-[0-9]+"]',
                'redact_replacement = "[hidden]"',
                "retention_runs = 5",
                "retention_days = 14",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["artifacts"] == {
        "redact_patterns": ["(?i)secret-[0-9]+"],
        "redact_replacement": "[hidden]",
        "retention_runs": 5,
        "retention_days": 14,
    }


def test_load_repo_config_reads_custom_profiles(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'default_profile = "team"',
                "",
                "[quality_runner.profiles.team]",
                'extends = "default"',
                'required_capabilities = ["lint", "tests"]',
                'allowed_package_managers = ["pnpm", "bun"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["default_profile"] == "team"
    assert config["profiles"] == {
        "team": {
            "extends": "default",
            "required_capabilities": ["lint", "tests"],
            "required_capabilities_configured": True,
            "allowed_package_managers": ["pnpm", "bun"],
        }
    }


def test_load_repo_config_reads_structural_scan_policy_and_accepted_dispositions(
    tmp_path,
) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                "",
                "[quality_runner.structural_scan]",
                'disabled_rule_groups = ["ui_structural", "speed"]',
                'include_ignored_paths = [".aios/shadow-worktrees/approved"]',
                "large_file_lines = 900",
                "fat_router_lines = 300",
                "",
                "[[quality_runner.accepted_dispositions]]",
                'fingerprint = "abc123"',
                'status = "accepted-false-positive"',
                'reason = "Generated wrapper is scanned as source."',
                'owner = "platform"',
                'expires = "2999-01-01"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["structural_scan"] == {
        "disabled_rule_groups": ["ui_structural", "speed"],
        "include_ignored_paths": [".aios/shadow-worktrees/approved"],
        "large_file_lines": 900,
        "fat_router_lines": 300,
    }
    assert config["accepted_dispositions"] == [
        {
            "fingerprint": "abc123",
            "status": "accepted-false-positive",
            "reason": "Generated wrapper is scanned as source.",
            "owner": "platform",
            "expires": "2999-01-01",
        }
    ]


def test_load_repo_config_reads_integrate_policy(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.integrate]",
                "enabled = false",
                'registration_globs = ["src/cli.py"]',
                'entrypoint_globs = ["src/main.py"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["integrate"] == {
        "enabled": False,
        "registration_globs": ["src/cli.py"],
        "entrypoint_globs": ["src/main.py"],
    }


def test_load_repo_config_reads_architecture_contract(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.architecture]",
                "enabled = true",
                "",
                "[[quality_runner.architecture.import_boundaries]]",
                'id = "ui-no-server-imports"',
                'sources = ["apps/web/**"]',
                'disallowed_imports = ["server/**"]',
                'allowed_imports = ["packages/domain/types/**"]',
                'severity = "warning"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["architecture"] == {
        "enabled": True,
        "import_boundaries": [
            {
                "id": "ui-no-server-imports",
                "sources": ["apps/web/**"],
                "disallowed_imports": ["server/**"],
                "allowed_imports": ["packages/domain/types/**"],
                "severity": "warning",
            }
        ],
    }


def test_load_repo_config_reports_missing_invalid_and_malformed_values(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    assert load_repo_config(tmp_path) == {
        "schema": "quality-runner-config-v0.1",
        "path": None,
        "default_profile": None,
        "profiles": {},
        "required_capabilities": [],
        "required_capabilities_configured": False,
        "allowed_package_managers": [],
        "scan_exclusions": [],
        "accepted_exceptions": [],
        "accepted_dispositions": [],
        "gates": [],
        "gate_timeouts": {},
        "severity_overrides": {},
        "structural_scan": {},
        "warnings": [],
    }

    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner\n",
        encoding="utf-8",
    )
    invalid = load_repo_config(tmp_path)

    assert invalid["path"] == ".quality-runner.toml"
    assert invalid["default_profile"] is None
    assert invalid["required_capabilities"] == []
    assert invalid["required_capabilities_configured"] is False
    assert invalid["allowed_package_managers"] == []
    assert invalid["scan_exclusions"] == []
    assert invalid["accepted_exceptions"] == []
    assert invalid["accepted_dispositions"] == []
    assert invalid["gates"] == []
    assert invalid["severity_overrides"] == {}
    assert invalid["structural_scan"] == {}
    assert invalid["warnings"][0]["code"] == "invalid_quality_runner_config"

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                "default_profile = 42",
                'required_capabilities = ["lint", 42]',
                'allowed_package_managers = ["pnpm", 42]',
                'scan_exclusions = ["samples", 42]',
                'accepted_exceptions = "not-a-list"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    malformed = load_repo_config(tmp_path)

    assert malformed["default_profile"] is None
    assert malformed["required_capabilities"] == []
    assert malformed["allowed_package_managers"] == []
    assert malformed["scan_exclusions"] == []
    assert malformed["required_capabilities_configured"] is True
    assert malformed["accepted_exceptions"] == []
    assert malformed["gate_timeouts"] == {}
    assert [warning["code"] for warning in malformed["warnings"]] == [
        "invalid_quality_runner_config_field",
        "invalid_quality_runner_config_field",
        "invalid_quality_runner_config_field",
        "invalid_quality_runner_config_field",
        "invalid_quality_runner_config_field",
    ]

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'accepted_exceptions = ["not-a-table", { capability = "tests" }]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    malformed_exceptions = load_repo_config(tmp_path)

    assert malformed_exceptions["accepted_exceptions"] == []
    assert [warning["message"] for warning in malformed_exceptions["warnings"]] == [
        "quality_runner.accepted_exceptions[0] must include capability, reason, owner, and expires strings",
        "quality_runner.accepted_exceptions[1] must include capability, reason, owner, and expires strings",
    ]

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'accepted_dispositions = [{ fingerprint = "abc123", status = "unresolved", reason = "not accepted", owner = "qa" }]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    malformed_dispositions = load_repo_config(tmp_path)

    assert malformed_dispositions["accepted_dispositions"] == []
    assert [warning["message"] for warning in malformed_dispositions["warnings"]] == [
        "quality_runner.accepted_dispositions[0] must include fingerprint, status, reason, owner, and optional expires strings",
    ]

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                'accepted_exceptions = [{ capability = "tests" }]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    missing_section = load_repo_config(tmp_path)

    assert missing_section["path"] == ".quality-runner.toml"
    assert missing_section["warnings"] == []


def test_load_repo_config_reads_scan_exclusions(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'scan_exclusions = ["samples", "generated-reports/**"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["scan_exclusions"] == ["samples", "generated-reports/**"]
    assert config["warnings"] == []


def test_detect_capabilities_applies_required_capabilities_and_active_exceptions(tmp_path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"lint": "eslint ."}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["lint", "tests", "truth_file"]',
                "",
                "[[quality_runner.accepted_exceptions]]",
                'capability = "truth_file"',
                'reason = "Truth file will be added after bootstrap."',
                'owner = "platform"',
                'expires = "2999-01-01"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="config-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert {item["id"] for item in capability_map["available"]} == {"lint"}
    assert capability_map["missing"] == [
        {
            "id": "tests",
            "type": "command",
            "reason": "no quality command found for tests",
            "language": "javascript",
            "required_by": "config",
        }
    ]
    assert capability_map["accepted_exceptions"] == [
        {
            "capability": "truth_file",
            "reason": "Truth file will be added after bootstrap.",
            "owner": "platform",
            "expires": "2999-01-01",
        }
    ]


def test_configured_gates_satisfy_capabilities_and_policy_metadata_reaches_audit(
    tmp_path,
) -> None:
    from quality_runner.audit import build_audit_report
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["lint", "tests"]',
                "",
                "[quality_runner.severity_overrides]",
                'missing-tests = "critical"',
                "",
                "[[quality_runner.gates]]",
                'id = "lint"',
                'command = "python -c \\"raise SystemExit(99)\\""',
                'ecosystem = "python"',
                'source = "local policy"',
                'owner = "platform"',
                "required = true",
                'severity = "blocker"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="policy-gate-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)
    report = build_audit_report(scan=scan, standards_packet=packet, capability_map=capability_map)

    assert capability_map["available"] == [
        {
            "id": "lint",
            "type": "command",
            "source": ".quality-runner.toml:quality_runner.gates[0]",
            "command": 'python -c "raise SystemExit(99)"',
            "language": "python",
            "capability_kind": "local_command",
            "required_by": "config",
            "owner": "platform",
            "severity": "blocker",
            "verification_state": {
                "discovery": "command-discovered",
                "execution": "not-run",
                "result": "unknown",
            },
        }
    ]
    assert capability_map["missing"] == [
        {
            "id": "tests",
            "type": "command",
            "reason": "no quality command found for tests",
            "language": "unknown",
            "required_by": "config",
        }
    ]
    assert report["findings"][0]["id"] == "missing-tests"
    assert report["findings"][0]["severity"] == "critical"
    assert report["findings"][0]["owner"] is None


def test_detect_capabilities_handles_file_sources_and_inactive_exceptions(tmp_path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    tracker = tmp_path / ".tracker"
    tracker.mkdir()
    (tracker / "PROJECT_TRUTH.md").write_text("# Truth\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"pre-cr": "pre-cr run"}}),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["pre_cr", "truth_file", "tests", "not_real"]',
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
        {
            "id": "truth_file",
            "type": "file",
            "capability_kind": "evidence_file",
            "source": ".tracker/PROJECT_TRUTH.md",
            "required_by": "config",
            "verification_state": {
                "discovery": "file-discovered",
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
        "review-manifest.schema.json",
        "review-delta.schema.json",
        "remediation-delta.schema.json",
        "plan-config.schema.json",
        "roadmap.schema.json",
        "planning-state.schema.json",
        "phase-plan.schema.json",
        "phase-batch-result.schema.json",
        "phase-verification.schema.json",
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
