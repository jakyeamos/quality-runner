from __future__ import annotations

import json
import sys
from pathlib import Path

from test_support.quality_runner_fixtures import write_complete_js_fixture


def test_run_payload_records_package_manager_mismatch_in_audit_and_plan(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import run_payload

    write_complete_js_fixture(tmp_path)
    package_json_path = tmp_path / "package.json"
    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    package_json["packageManager"] = "npm@10.0.0"
    package_json_path.write_text(json.dumps(package_json), encoding="utf-8")

    payload = run_payload(repo_root=tmp_path, run_id="mismatch-run", profile="default")
    audit_report = json.loads(Path(payload["artifact_paths"]["quality_audit_json"]).read_text())
    remediation_plan = json.loads(
        Path(payload["artifact_paths"]["remediation_plan_json"]).read_text()
    )

    mismatch_finding = next(
        finding
        for finding in audit_report["findings"]
        if finding["id"] == "standard-package-manager-mismatch"
    )
    assert mismatch_finding["severity"] == "warning"
    assert mismatch_finding["evidence"] == [
        "Expected package manager: pnpm.",
        "Detected package manager: npm.",
        "Package manager source: package.json packageManager or lockfile discovery.",
    ]
    assert (
        mismatch_finding["recommended_fix"]
        == "Align JavaScript dependency management to the pnpm standard."
    )
    assert any(
        slice_item["findings"][0]["id"] == "standard-package-manager-mismatch"
        for slice_item in remediation_plan["slices"]
    )


def test_inspect_payload_writes_package_manager_preflight_artifact(tmp_path: Path) -> None:
    from quality_runner.workflow import inspect_payload

    write_complete_js_fixture(tmp_path)
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")

    payload = inspect_payload(repo_root=tmp_path, run_id="package-preflight-run", profile="default")
    preflight = json.loads(
        Path(payload["artifact_paths"]["package_manager_preflight_json"]).read_text()
    )

    assert preflight["schema"] == "quality-runner-package-manager-preflight-v0.1"
    assert preflight["status"] == "warning"
    assert preflight["package_manager"] == "pnpm"
    assert preflight["lockfiles"] == ["package-lock.json", "pnpm-lock.yaml"]
    assert preflight["warnings"] == [
        {
            "code": "multiple_lockfiles",
            "message": "Multiple JavaScript package-manager lockfiles are present.",
            "path": ".",
        }
    ]


def test_verify_gates_payload_executes_discovered_gates_and_marks_capabilities(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import verify_gates_payload

    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "lint": f"{sys.executable} -c 'import sys; sys.exit(0)'",
                    "test": f"{sys.executable} -c 'import sys; sys.exit(1)'",
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'required_capabilities = ["lint", "tests"]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = verify_gates_payload(repo_root=tmp_path, run_id="verify-gates-run", profile="default")
    verification = json.loads(
        Path(payload["artifact_paths"]["gate_verification_json"]).read_text()
    )
    capability_map = json.loads(
        Path(payload["artifact_paths"]["capability_matrix_json"]).read_text()
    )

    assert payload["schema"] == "quality-runner-verify-gates-result-v0.1"
    assert payload["status"] == "failed"
    assert verification["schema"] == "quality-runner-gate-verification-v0.1"
    assert [(gate["id"], gate["status"], gate["exit_code"]) for gate in verification["gates"]] == [
        ("lint", "passed", 0),
        ("tests", "failed", 1),
    ]
    states = {
        capability["id"]: capability["verification_state"]
        for capability in capability_map["available"]
    }
    assert states["lint"] == {
        "discovery": "command-discovered",
        "execution": "local-executed",
        "result": "passed",
    }
    assert states["tests"] == {
        "discovery": "command-discovered",
        "execution": "local-executed",
        "result": "failed",
    }
