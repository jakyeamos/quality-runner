from __future__ import annotations

import json


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
                'capability = "unused_capability"',
                'reason = "Fixture repo has an unused capability."',
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
                "capability": "unused_capability",
                "reason": "Fixture repo has an unused capability.",
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
                'mutating_risk = "unknown"',
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
            "mutating_risk": "unknown",
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


def test_load_repo_config_reads_compact_grouped_dispositions_without_local_config(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner-dispositions.toml").write_text(
        "\n".join(
            [
                'schema = "quality-runner-dispositions-v1"',
                "",
                "[[quality_runner.accepted_disposition_groups]]",
                'status = "accepted-false-positive"',
                'reason = "Safe fixture values."',
                'owner = "security"',
                'expires = "2999-01-01"',
                'source_run_id = "qr-test"',
                'review_evidence = ["evidence.md"]',
                'fingerprints = ["sec-one", "sec-two"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["path"] == ".quality-runner-dispositions.toml"
    assert config["warnings"] == []
    assert config["accepted_dispositions"] == [
        {
            "fingerprint": "sec-one",
            "status": "accepted-false-positive",
            "reason": "Safe fixture values.",
            "owner": "security",
            "expires": "2999-01-01",
            "source_run_id": "qr-test",
            "review_evidence": ["evidence.md"],
        },
        {
            "fingerprint": "sec-two",
            "status": "accepted-false-positive",
            "reason": "Safe fixture values.",
            "owner": "security",
            "expires": "2999-01-01",
            "source_run_id": "qr-test",
            "review_evidence": ["evidence.md"],
        },
    ]


def test_load_repo_config_rejects_duplicate_grouped_fingerprints(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner-dispositions.toml").write_text(
        "\n".join(
            [
                'schema = "quality-runner-dispositions-v1"',
                "",
                "[[quality_runner.accepted_disposition_groups]]",
                'status = "accepted-false-positive"',
                'reason = "First."',
                'owner = "security"',
                'fingerprints = ["sec-duplicate"]',
                "",
                "[[quality_runner.accepted_disposition_groups]]",
                'status = "accepted-false-positive"',
                'reason = "Second."',
                'owner = "security"',
                'fingerprints = ["sec-duplicate"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert len(config["accepted_dispositions"]) == 1
    assert config["accepted_dispositions"][0]["reason"] == "First."
    assert config["warnings"][0]["code"] == "invalid_quality_runner_dispositions"


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
                'required_capabilities = ["lint", "tests"]',
                "",
                "[[quality_runner.accepted_exceptions]]",
                'capability = "state_file"',
                'reason = "Planning context is optional."',
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
    assert capability_map["accepted_exceptions"] == []


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
                'mutating_risk = "mutating"',
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
            "mutating_risk": "mutating",
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
