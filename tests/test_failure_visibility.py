from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def test_failure_visibility_is_opt_in_and_discovered_as_a_local_gate(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"failure-visibility": "node scripts/failure-visibility.mjs"}}),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="failure-visibility-default")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    default_map = detect_capabilities(scan=scan, standards_packet=packet)
    assert "failure_visibility" not in {item["id"] for item in default_map["available"]}
    assert "failure_visibility" not in {item["id"] for item in default_map["missing"]}

    release_packet = compile_standards(repo_root=tmp_path, scan=scan, profile="release")
    release_map = detect_capabilities(scan=scan, standards_packet=release_packet)
    assert "failure_visibility" not in {item["id"] for item in release_map["available"]}
    assert "failure_visibility" not in {item["id"] for item in release_map["missing"]}

    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nrequired_capabilities = ["failure_visibility"]\n',
        encoding="utf-8",
    )
    scan = inspect_repo(tmp_path, run_id="failure-visibility-opt-in")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert capability_map["available"] == [
        {
            "id": "failure_visibility",
            "type": "command",
            "capability_kind": "local_command",
            "source": "package.json:scripts.failure-visibility",
            "command": "node scripts/failure-visibility.mjs",
            "language": "javascript",
            "required_by": "config",
            "evidence_state": "configured",
            "verification_state": {
                "discovery": "command-discovered",
                "execution": "not-run",
                "result": "unknown",
            },
        }
    ]


def test_capability_evidence_state_requires_fresh_commit_bound_ci() -> None:
    from quality_runner.capability_state import capability_evidence_state, matching_ci_status

    scan = {"git_provenance": {"head_sha": "abc123", "branch": "main"}}
    current = {
        "conclusion": "success",
        "head_sha": "abc123",
        "ref": "refs/heads/main",
        "workflow_run_id": "run-1",
        "captured_at": datetime.now(UTC).isoformat(),
    }

    assert capability_evidence_state(scan=scan, ci_status=current) == "fresh_passing"
    assert (
        capability_evidence_state(scan=scan, ci_status={**current, "head_sha": "old"}) == "covered"
    )
    assert (
        capability_evidence_state(scan=scan, ci_status={**current, "conclusion": "failure"})
        == "failed"
    )

    scan["ci_checks"] = [{"name": "Failure visibility", **current}]
    matched = matching_ci_status(scan, "failure_visibility")
    assert matched is not None
    assert capability_evidence_state(scan=scan, ci_status=matched) == "fresh_passing"


def test_missing_failure_visibility_and_exception_states_are_explicit(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["failure_visibility"]',
                "",
                "[[quality_runner.accepted_exceptions]]",
                'capability = "failure_visibility"',
                'reason = "Negative-path harness is being migrated."',
                'owner = "platform"',
                'expires = "2999-01-01"',
            ]
        ),
        encoding="utf-8",
    )
    scan = inspect_repo(tmp_path, run_id="failure-visibility-exception")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="default")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert capability_map["missing"] == []
    assert capability_map["accepted_exceptions"] == [
        {
            "capability": "failure_visibility",
            "reason": "Negative-path harness is being migrated.",
            "owner": "platform",
            "expires": "2999-01-01",
            "evidence_state": "not_applicable",
        }
    ]


def test_python_silent_except_is_reported_but_observable_handling_is_not(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    (tmp_path / "service.py").write_text(
        "\n".join(
            [
                "def hidden():",
                "    try:",
                "        run()",
                "    except RuntimeError:",
                "        pass",
                "",
                "def visible():",
                "    try:",
                "        run()",
                "    except RuntimeError as error:",
                "        raise VisibleFailure() from error",
            ]
        ),
        encoding="utf-8",
    )

    result = create_code_quality_scan(tmp_path, scan={"run_id": "silent-except"}, config={})
    findings = [item for item in result["findings"] if item["rule_id"] == "silent-except-pass"]
    assert [(item["file"], item["line"]) for item in findings] == [("service.py", 4)]


def test_failure_visibility_gate_results_are_executed_and_projected(tmp_path: Path) -> None:
    from quality_runner.gate_verification import apply_gate_verification, verify_discovered_gates

    for expected_status, exit_code in (("passed", 0), ("failed", 7)):
        execution_root = tmp_path / f"execution-{expected_status}"
        execution_root.mkdir()
        capability_map = {
            "available": [
                {
                    "id": "failure_visibility",
                    "type": "command",
                    "capability_kind": "local_command",
                    "source": ".quality-runner.toml:quality_runner.gates[0]",
                    "command": f'python -c "raise SystemExit({exit_code})"',
                    "language": "python",
                    "evidence_state": "configured",
                    "verification_state": {
                        "discovery": "command-discovered",
                        "execution": "not-run",
                        "result": "unknown",
                    },
                }
            ],
            "missing": [],
        }

        verification = verify_discovered_gates(
            repo_root=tmp_path,
            capability_map=capability_map,
            execute_discovered_gates=True,
            execution_root=execution_root,
            mutations_isolated=True,
        )
        updated = apply_gate_verification(capability_map, verification)

        assert [
            (gate["id"], gate["status"], gate["exit_code"]) for gate in verification["gates"]
        ] == [("failure_visibility", expected_status, exit_code)]
        assert updated["available"][0]["evidence_state"] == (
            "fresh_passing" if expected_status == "passed" else "failed"
        )
