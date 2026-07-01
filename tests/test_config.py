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
                'default_profile = "jakyeamos"',
                'required_capabilities = ["lint", "tests"]',
                "",
                "[[quality_runner.accepted_exceptions]]",
                'capability = "truth_file"',
                'reason = "Fixture repo has no project truth file."',
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
        "default_profile": "jakyeamos",
        "required_capabilities": ["lint", "tests"],
        "required_capabilities_configured": True,
        "accepted_exceptions": [
            {
                "capability": "truth_file",
                "reason": "Fixture repo has no project truth file.",
                "expires": "2999-01-01",
            }
        ],
        "warnings": [],
    }


def test_load_repo_config_reports_missing_invalid_and_malformed_values(tmp_path) -> None:
    from quality_runner.config import load_repo_config

    assert load_repo_config(tmp_path) == {
        "schema": "quality-runner-config-v0.1",
        "path": None,
        "default_profile": None,
        "required_capabilities": [],
        "required_capabilities_configured": False,
        "accepted_exceptions": [],
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
    assert invalid["accepted_exceptions"] == []
    assert invalid["warnings"][0]["code"] == "invalid_quality_runner_config"

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                "default_profile = 42",
                'required_capabilities = ["lint", 42]',
                'accepted_exceptions = "not-a-list"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    malformed = load_repo_config(tmp_path)

    assert malformed["default_profile"] is None
    assert malformed["required_capabilities"] == []
    assert malformed["required_capabilities_configured"] is True
    assert malformed["accepted_exceptions"] == []
    assert [warning["code"] for warning in malformed["warnings"]] == [
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
        "quality_runner.accepted_exceptions[0] must include capability, reason, and expires strings",
        "quality_runner.accepted_exceptions[1] must include capability, reason, and expires strings",
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
                'expires = "2999-01-01"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="config-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert {item["id"] for item in capability_map["available"]} == {"lint"}
    assert capability_map["missing"] == [
        {
            "id": "tests",
            "type": "command",
            "reason": "no quality command found for tests",
            "language": "javascript",
        }
    ]
    assert capability_map["accepted_exceptions"] == [
        {
            "capability": "truth_file",
            "reason": "Truth file will be added after bootstrap.",
            "expires": "2999-01-01",
        }
    ]


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
                'expires = "2000-01-01"',
                "",
                "[[quality_runner.accepted_exceptions]]",
                'capability = "tests"',
                'reason = "Invalid expiry should not suppress missing tests."',
                'expires = "not-a-date"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="config-002")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert capability_map["available"] == [
        {
            "id": "pre_cr",
            "type": "command",
            "source": "package.json:scripts.pre-cr",
            "command": "pre-cr run",
            "language": "javascript",
        },
        {"id": "truth_file", "type": "file", "source": ".tracker/PROJECT_TRUTH.md"},
    ]
    assert capability_map["missing"] == [
        {
            "id": "tests",
            "type": "command",
            "reason": "no quality command found for tests",
            "language": "javascript",
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
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert capability_map["available"] == []
    assert capability_map["missing"] == []
    assert capability_map["accepted_exceptions"] == []


def test_workflow_uses_config_default_profile_when_profile_is_omitted(tmp_path) -> None:
    from quality_runner.workflow import inspect_payload

    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\ndefault_profile = "jakyeamos"\n',
        encoding="utf-8",
    )

    payload = inspect_payload(repo_root=tmp_path, run_id="config-profile")
    standards = json.loads(
        (tmp_path / ".quality-runner" / "runs" / "config-profile" / "standards.json").read_text()
    )

    assert payload["schema"] == "quality-runner-inspect-result-v0.1"
    assert standards["profile"] == "jakyeamos"
    assert {"type": "config", "path": ".quality-runner.toml"} in standards["sources"]


def test_workflow_allows_explicit_profile_to_override_config_default(tmp_path) -> None:
    from quality_runner.workflow import run_payload

    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\ndefault_profile = "jakyeamos"\nrequired_capabilities = []\n',
        encoding="utf-8",
    )

    payload = run_payload(repo_root=tmp_path, run_id="config-run", profile="jakyeamos")
    standards = json.loads(
        (tmp_path / ".quality-runner" / "runs" / "config-run" / "standards.json").read_text()
    )

    assert payload["status"] == "clean"
    assert standards["profile"] == "jakyeamos"


def test_packaged_schema_files_are_parseable() -> None:
    schema_root = resources.files("quality_runner").joinpath("schemas")
    schema_names = {
        "repo-scan.schema.json",
        "standards.schema.json",
        "capability-matrix.schema.json",
        "quality-audit.schema.json",
        "remediation-plan.schema.json",
        "agent-handoff.schema.json",
        "run-manifest.schema.json",
        "run-result.schema.json",
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
