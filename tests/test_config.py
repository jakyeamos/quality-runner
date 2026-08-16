from __future__ import annotations


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
        "invariants": [],
        "gate_timeouts": {},
        "severity_overrides": {},
        "structural_scan": {},
        "warnings": [],
    }


def test_load_repo_config_reads_explicit_prevention_policy(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.prevention]",
                'required_modules = ["code_quality"]',
                'environment_paths = [".venv/bin"]',
                'snapshot_include_paths = ["dist/declared.json"]',
                "",
                "[[quality_runner.prevention.rules]]",
                'detector = "code_quality"',
                'rule_id = "large-source-file"',
                'state = "behavior-verified"',
                'owner = "quality"',
                'rationale = "Large files increase review risk."',
                'evidence_refs = ["positive:large.py", "negative:small.py", "ambiguous:generated.py"]',
                'paths = ["src/**"]',
                "confidence_threshold = 1.0",
                "",
                "[[quality_runner.prevention.gates]]",
                'id = "lint"',
                'command = "ruff check ."',
                'state = "certified"',
                "required = true",
                'owner = "quality"',
                'rationale = "Deterministic lint."',
                'bootstrap = "uv sync --frozen"',
                'mutation_risk = "read-only"',
                'scope = "Python source"',
                "timeout_seconds = 60",
                'evidence_refs = ["failure-fixture:lint.py", "repeat-pass:lint.json", "local:run.json", "ci:ci.yml"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    prevention = load_repo_config(tmp_path)["prevention"]

    assert prevention["required_modules"] == ["code_quality"]
    assert prevention["environment_paths"] == [".venv/bin"]
    assert prevention["snapshot_include_paths"] == ["dist/declared.json"]
    assert prevention["rules"][0]["state"] == "behavior-verified"
    assert prevention["gates"][0]["state"] == "certified"


def test_load_repo_config_preserves_declared_unavailable_gate(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[[quality_runner.prevention.gates]]",
                'id = "smoke"',
                'command = "pnpm smoke"',
                'state = "unavailable"',
                "required = false",
                'owner = "quality"',
                'rationale = "The script is not defined."',
                'bootstrap = "pnpm install --frozen-lockfile"',
                'mutation_risk = "isolated-only"',
                'blocker = "package.json has no smoke script"',
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert config["warnings"] == []
    assert config["prevention"]["gates"][0]["state"] == "unavailable"
    assert config["prevention"]["gates"][0]["blocker"] == "package.json has no smoke script"


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
        "invariants": [],
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
