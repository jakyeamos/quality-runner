from __future__ import annotations

import json
import subprocess
from pathlib import Path

from test_support.quality_runner_fixtures import (
    write_complete_js_fixture,
    write_js_fixture,
    write_python_quality_fixture,
)


def _git_commit(repo_root: Path) -> str:
    subprocess.run(["git", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    (repo_root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo_root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=quality-runner@example.com",
            "-c",
            "user.name=Quality Runner",
            "commit",
            "-m",
            "Initial commit",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_run_payload_writes_audit_plan_and_handoff(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    write_js_fixture(tmp_path)

    payload = run_payload(repo_root=tmp_path, run_id="run-001", profile="jakyeamos")

    assert payload["schema"] == "quality-runner-run-result-v0.1"
    assert payload["status"] == "planned"
    assert payload["implementation_allowed"] is False
    artifact_paths = payload["artifact_paths"]
    assert set(artifact_paths) == {
        "repo_scan_json",
        "code_quality_scan_json",
        "standards_json",
        "capability_matrix_json",
        "run_manifest_json",
        "quality_audit_json",
        "remediation_plan_json",
        "resolution_ledger_json",
        "resolution_ledger_md",
        "agent_handoff_json",
        "agent_handoff_md",
    }
    assert Path(artifact_paths["standards_json"]).name == "standards.json"
    assert Path(artifact_paths["capability_matrix_json"]).name == "capability-matrix.json"
    assert Path(artifact_paths["quality_audit_json"]).name == "quality-audit.json"
    assert Path(artifact_paths["repo_scan_json"]).exists()
    assert Path(artifact_paths["standards_json"]).exists()
    assert Path(artifact_paths["capability_matrix_json"]).exists()
    assert Path(artifact_paths["run_manifest_json"]).exists()
    assert Path(artifact_paths["quality_audit_json"]).exists()
    assert Path(artifact_paths["code_quality_scan_json"]).exists()
    assert Path(artifact_paths["resolution_ledger_json"]).exists()
    assert Path(artifact_paths["resolution_ledger_md"]).exists()
    assert Path(artifact_paths["remediation_plan_json"]).exists()
    assert Path(artifact_paths["agent_handoff_md"]).exists()
    run_dir = Path(artifact_paths["repo_scan_json"]).parent
    legacy_names = {
        "standards-packet.json",
        "capability-map.json",
        "audit-report.json",
        "audit-report.md",
        "remediation-plan.md",
    }
    assert not any((run_dir / name).exists() for name in legacy_names)


def test_run_payload_adds_structural_findings_and_groups_remediation_slices(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import run_payload

    write_complete_js_fixture(tmp_path)
    source = tmp_path / "src" / "app" / "page.tsx"
    source.parent.mkdir(parents=True)
    source.write_text(
        "\n".join(
            [
                "import { trpc } from '@/lib/trpc';",
                "export default function Page() {",
                "  const user = trpc.user.me.useQuery();",
                "  const first: any = user.data;",
                "  const second: any = user.error;",
                '  return <main><div className="card"><div className="card">Nested</div></div></main>;',
                "}",
            ]
        ),
        encoding="utf-8",
    )

    payload = run_payload(repo_root=tmp_path, run_id="structural-run", profile="jakyeamos")

    code_scan = json.loads(Path(payload["artifact_paths"]["code_quality_scan_json"]).read_text())
    audit_report = json.loads(Path(payload["artifact_paths"]["quality_audit_json"]).read_text())
    remediation_plan = json.loads(
        Path(payload["artifact_paths"]["remediation_plan_json"]).read_text()
    )
    handoff = json.loads(Path(payload["artifact_paths"]["agent_handoff_json"]).read_text())

    structural_rules = {finding["rule_id"] for finding in code_scan["findings"]}
    assert {"explicit-any", "nested-card-markup"} <= structural_rules
    audit_ids = {finding["id"] for finding in audit_report["findings"]}
    assert any(finding_id.startswith("structural-") for finding_id in audit_ids)
    explicit_any_slices = [
        slice_item
        for slice_item in remediation_plan["slices"]
        if slice_item["id"] == "remediate-structural-harden-explicit-any"
    ]
    assert len(explicit_any_slices) == 1
    assert len(explicit_any_slices[0]["findings"]) == 1
    assert "2 findings" in explicit_any_slices[0]["actions"][0]
    assert handoff["next_slice"]["id"] == remediation_plan["slices"][0]["id"]


def test_resolution_ledger_marks_missing_prior_findings_fixed_and_preserves_acceptance(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import run_payload

    write_complete_js_fixture(tmp_path)
    source = tmp_path / "src" / "index.ts"
    source.parent.mkdir(parents=True)
    source.write_text("const first: any = {};\n", encoding="utf-8")

    first_payload = run_payload(repo_root=tmp_path, run_id="ledger-first", profile="jakyeamos")
    first_scan = json.loads(
        Path(first_payload["artifact_paths"]["code_quality_scan_json"]).read_text()
    )
    explicit_any = next(
        finding for finding in first_scan["findings"] if finding["rule_id"] == "explicit-any"
    )

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                "",
                "[[quality_runner.accepted_dispositions]]",
                f'fingerprint = "{explicit_any["fingerprint"]}"',
                'status = "accepted-intentional"',
                'reason = "Fixture intentionally keeps one type escape hatch."',
                'owner = "qa"',
                'expires = "2999-01-01"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    accepted_payload = run_payload(
        repo_root=tmp_path, run_id="ledger-accepted", profile="jakyeamos"
    )
    accepted_ledger = json.loads(
        Path(accepted_payload["artifact_paths"]["resolution_ledger_json"]).read_text()
    )
    accepted_row = next(
        row
        for row in accepted_ledger["entries"]
        if row["fingerprint"] == explicit_any["fingerprint"]
    )
    assert accepted_row["status"] == "accepted-intentional"
    assert accepted_row["reason"] == "Fixture intentionally keeps one type escape hatch."

    source.write_text("const first: unknown = {};\n", encoding="utf-8")
    fixed_payload = run_payload(repo_root=tmp_path, run_id="ledger-fixed", profile="jakyeamos")
    fixed_ledger = json.loads(
        Path(fixed_payload["artifact_paths"]["resolution_ledger_json"]).read_text()
    )
    fixed_row = next(
        row for row in fixed_ledger["entries"] if row["fingerprint"] == explicit_any["fingerprint"]
    )
    assert fixed_row["status"] == "fixed"


def test_workflow_ingests_local_ci_status_and_attaches_check_evidence(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"lint": "eslint .", "test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    workflow_root = tmp_path / ".github" / "workflows"
    workflow_root.mkdir(parents=True)
    (workflow_root / "ci.yml").write_text(
        "\n".join(
            [
                "name: CI",
                "on:",
                "  pull_request:",
                "jobs:",
                "  quality:",
                "    name: Quality",
                "    steps:",
                "      - name: Lint",
                "        run: pnpm lint",
                "      - name: Tests",
                "        run: pnpm test",
                "",
            ]
        ),
        encoding="utf-8",
    )
    ci_status = tmp_path / "ci-status.json"
    ci_status.write_text(
        json.dumps(
            {
                "checks": [
                    {
                        "name": "Quality / Lint",
                        "status": "completed",
                        "conclusion": "success",
                        "url": "https://example.invalid/check/lint",
                    },
                    {
                        "name": "Quality / Tests",
                        "status": "completed",
                        "conclusion": "failure",
                        "url": "https://example.invalid/check/tests",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = run_payload(repo_root=tmp_path, run_id="ci-status-run", ci_status_json=ci_status)

    repo_scan = json.loads(Path(payload["artifact_paths"]["repo_scan_json"]).read_text())
    capability_map = json.loads(
        Path(payload["artifact_paths"]["capability_matrix_json"]).read_text()
    )
    assert repo_scan["ci_checks"] == [
        {
            "name": "Quality / Lint",
            "status": "completed",
            "conclusion": "success",
            "url": "https://example.invalid/check/lint",
            "source": "ci-status.json",
        },
        {
            "name": "Quality / Tests",
            "status": "completed",
            "conclusion": "failure",
            "url": "https://example.invalid/check/tests",
            "source": "ci-status.json",
        },
    ]
    available = {item["id"]: item for item in capability_map["available"]}
    assert available["lint"]["ci_status"] == {
        "name": "Quality / Lint",
        "status": "completed",
        "conclusion": "success",
        "url": "https://example.invalid/check/lint",
    }
    assert available["tests"]["ci_status"]["conclusion"] == "failure"


def test_workflow_warns_on_malformed_local_ci_status(tmp_path: Path) -> None:
    from quality_runner.workflow import inspect_payload

    ci_status = tmp_path / "ci-status.json"
    ci_status.write_text("{not-json", encoding="utf-8")

    payload = inspect_payload(repo_root=tmp_path, run_id="bad-ci-status", ci_status_json=ci_status)

    assert {
        "code": "invalid_ci_status_json",
        "message": "ci-status.json could not be parsed as JSON",
        "path": "ci-status.json",
    } in payload["warnings"]


def test_run_payload_writes_manifest_with_git_head(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    head_sha = _git_commit(tmp_path)

    payload = run_payload(repo_root=tmp_path, run_id="manifest-run", profile="jakyeamos")
    manifest = json.loads(Path(payload["artifact_paths"]["run_manifest_json"]).read_text())

    assert manifest["schema"] == "quality-runner-run-manifest-v0.1"
    assert manifest["mode"] == "run"
    assert manifest["run_id"] == "manifest-run"
    assert manifest["quality_runner_version"] == "0.2.0"
    assert manifest["git"]["head_sha"] == head_sha
    assert manifest["git"]["is_repo"] is True
    assert manifest["git"]["dirty"] is True
    assert manifest["artifact_paths"]["quality_audit_json"].endswith("quality-audit.json")


def test_run_payload_records_missing_capability_findings(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    payload = run_payload(repo_root=tmp_path, run_id="empty-run", profile="jakyeamos")
    audit_report = json.loads(Path(payload["artifact_paths"]["quality_audit_json"]).read_text())

    finding_ids = {finding["id"] for finding in audit_report["findings"]}
    assert "missing-lint" in finding_ids
    assert "missing-tests" in finding_ids
    assert "missing-truth-file" not in finding_ids


def test_run_payload_does_not_false_positive_python_quality_gates(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    write_python_quality_fixture(tmp_path)

    payload = run_payload(repo_root=tmp_path, run_id="python-quality-run", profile="jakyeamos")
    audit_report = json.loads(Path(payload["artifact_paths"]["quality_audit_json"]).read_text())
    capability_map = json.loads(
        Path(payload["artifact_paths"]["capability_matrix_json"]).read_text()
    )

    assert payload["status"] == "clean"
    finding_ids = {finding["id"] for finding in audit_report["findings"]}
    assert "missing-formatter" not in finding_ids
    assert "missing-lint" not in finding_ids
    assert "missing-typecheck" not in finding_ids
    assert "missing-tests" not in finding_ids
    assert "missing-build" not in finding_ids
    assert "missing-dead-code" not in finding_ids
    assert "missing-runtime-smoke" not in finding_ids
    assert "missing-pre-pr" not in finding_ids
    assert "missing-truth-file" not in finding_ids
    available = {item["id"]: item for item in capability_map["available"]}
    assert available["dead_code"]["source"] == ".github/workflows"
    assert available["runtime_smoke"]["command"] == "quality-runner doctor --json"


def test_run_payload_python_missing_gate_uses_python_recommendation(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "partial-python"',
                'version = "0.1.0"',
                "",
                "[tool.pytest.ini_options]",
                'pythonpath = ["."]',
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = run_payload(repo_root=tmp_path, run_id="python-missing-run", profile="jakyeamos")
    audit_report = json.loads(Path(payload["artifact_paths"]["quality_audit_json"]).read_text())
    lint_finding = next(
        finding for finding in audit_report["findings"] if finding["id"] == "missing-lint"
    )

    assert lint_finding["recommended_fix"] == "Add a Python lint gate such as ruff check ."


def test_run_payload_records_package_manager_mismatch_in_audit_and_plan(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import run_payload

    write_complete_js_fixture(tmp_path)
    package_json_path = tmp_path / "package.json"
    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    package_json["packageManager"] = "npm@10.0.0"
    package_json_path.write_text(json.dumps(package_json), encoding="utf-8")

    payload = run_payload(repo_root=tmp_path, run_id="mismatch-run", profile="jakyeamos")
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


def test_run_payload_records_missing_formatter_as_blocker(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    payload = run_payload(repo_root=tmp_path, run_id="missing-formatter-run", profile="jakyeamos")
    audit_report = json.loads(Path(payload["artifact_paths"]["quality_audit_json"]).read_text())

    formatter_finding = next(
        finding for finding in audit_report["findings"] if finding["id"] == "missing-formatter"
    )
    assert formatter_finding["severity"] == "blocker"


def test_inspect_payload_does_not_write_audit_plan(tmp_path: Path) -> None:
    from quality_runner.workflow import inspect_payload

    payload = inspect_payload(repo_root=tmp_path, run_id="inspect-001", profile="jakyeamos")

    assert payload["schema"] == "quality-runner-inspect-result-v0.1"
    assert Path(payload["artifact_paths"]["repo_scan_json"]).exists()
    assert Path(payload["artifact_paths"]["standards_json"]).name == "standards.json"
    assert (
        Path(payload["artifact_paths"]["capability_matrix_json"]).name == "capability-matrix.json"
    )
    assert Path(payload["artifact_paths"]["run_manifest_json"]).name == "run-manifest.json"
    assert "quality_audit_json" not in payload["artifact_paths"]


def test_inspect_payload_writes_manifest_without_git_repo(tmp_path: Path) -> None:
    from quality_runner.workflow import inspect_payload

    payload = inspect_payload(repo_root=tmp_path, run_id="inspect-manifest", profile="jakyeamos")
    manifest = json.loads(Path(payload["artifact_paths"]["run_manifest_json"]).read_text())

    assert manifest["schema"] == "quality-runner-run-manifest-v0.1"
    assert manifest["mode"] == "inspect"
    assert manifest["git"] == {
        "is_repo": False,
        "head_sha": None,
        "branch": None,
        "dirty": None,
    }


def test_run_manifest_handles_git_command_failures(tmp_path: Path, monkeypatch) -> None:
    import quality_runner.manifest as manifest

    (tmp_path / ".git").mkdir()

    def failed_git(*_: object, **__: object) -> object:
        raise OSError("git unavailable")

    monkeypatch.setattr(manifest.subprocess, "run", failed_git)

    payload = manifest.build_run_manifest(
        repo_root=tmp_path,
        run_id="git-failure",
        mode="run",
        artifact_paths={},
    )

    assert payload["git"] == {
        "is_repo": False,
        "head_sha": None,
        "branch": None,
        "dirty": None,
    }


def test_run_payload_rejects_unsafe_run_ids(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    try:
        run_payload(repo_root=tmp_path, run_id="../escape", profile="jakyeamos")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("run_payload accepted a parent traversal run ID")


def test_inspect_payload_rejects_unsafe_run_ids(tmp_path: Path) -> None:
    from quality_runner.workflow import inspect_payload

    try:
        inspect_payload(repo_root=tmp_path, run_id="nested/run", profile="jakyeamos")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("inspect_payload accepted a separator run ID")


def test_run_payload_rejects_symlinked_run_dir_without_external_writes(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    write_js_fixture(tmp_path)
    external = tmp_path.parent / f"{tmp_path.name}-external-artifacts"
    external.mkdir()
    runs_dir = tmp_path / ".quality-runner" / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "symlink-run").symlink_to(external, target_is_directory=True)

    try:
        run_payload(repo_root=tmp_path, run_id="symlink-run", profile="jakyeamos")
    except ValueError as error:
        assert str(error) == "artifact path component must not be a symlink"
    else:
        raise AssertionError("run_payload accepted a symlinked run directory")

    assert list(external.iterdir()) == []


def test_run_payload_rejects_symlinked_artifact_leaf_without_external_write(
    tmp_path: Path,
) -> None:
    from quality_runner.workflow import run_payload

    write_js_fixture(tmp_path)
    run_dir = tmp_path / ".quality-runner" / "runs" / "leaf-symlink-run"
    run_dir.mkdir(parents=True)
    external = tmp_path.parent / f"{tmp_path.name}-external-handoff.json"
    external.write_text("sentinel\n", encoding="utf-8")
    (run_dir / "agent-handoff.json").symlink_to(external)

    try:
        run_payload(repo_root=tmp_path, run_id="leaf-symlink-run", profile="jakyeamos")
    except ValueError as error:
        assert str(error) == "artifact file must not be a symlink"
    else:
        raise AssertionError("run_payload accepted a symlinked artifact leaf")

    assert external.read_text(encoding="utf-8") == "sentinel\n"


def test_generated_run_id_uses_explicit_suffix_for_collision_resistance() -> None:
    from datetime import UTC, datetime

    from quality_runner.workflow import generated_run_id

    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    assert generated_run_id(now=now, suffix="abcdef12") == "20260102T030405Z-abcdef12"


def test_run_payload_writes_handoff_warnings(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    (tmp_path / "package.json").write_text("{not-json", encoding="utf-8")

    payload = run_payload(repo_root=tmp_path, run_id="warning-run", profile="jakyeamos")
    handoff = json.loads(Path(payload["artifact_paths"]["agent_handoff_json"]).read_text())

    assert {
        "code": "invalid_package_json",
        "message": "package.json could not be parsed as JSON",
        "path": "package.json",
    } in handoff["warnings"]


def test_run_payload_handoff_contains_next_slice_and_verification_gates(tmp_path: Path) -> None:
    from quality_runner.findings import validate_agent_handoff
    from quality_runner.workflow import run_payload

    write_js_fixture(tmp_path)

    payload = run_payload(repo_root=tmp_path, run_id="handoff-context-run", profile="jakyeamos")
    handoff = json.loads(Path(payload["artifact_paths"]["agent_handoff_json"]).read_text())

    assert validate_agent_handoff(handoff) == {"passed": True, "errors": []}
    assert handoff["next_slice"] == {
        "id": "remediate-missing-formatter",
        "title": "Remediate missing-formatter",
        "priority": "high",
        "findings": [
            {
                "id": "missing-formatter",
                "severity": "blocker",
                "category": "capability",
                "summary": "Required quality capability is missing: formatter.",
            }
        ],
        "actions": [
            "Apply recommended fix: Add a formatter command such as pnpm format.",
            "Rerun quality-runner and confirm missing-formatter no longer appears.",
        ],
        "verification_gates": [
            "Add the formatter capability and rerun quality-runner.",
            "Confirm audit finding missing-formatter is absent from the regenerated report.",
        ],
    }
    assert handoff["verification_gates"] == [
        "Add the formatter capability and rerun quality-runner.",
        "Confirm audit finding missing-formatter is absent from the regenerated report.",
    ]


def test_run_payload_rejects_invalid_handoff_before_writing_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import quality_runner.workflow as workflow

    write_js_fixture(tmp_path)

    def invalid_handoff(**_: object) -> dict[str, object]:
        return {
            "schema": "quality-runner-agent-handoff-v0.1",
            "status": "planned",
            "implementation_allowed": False,
        }

    monkeypatch.setattr(workflow, "build_agent_handoff", invalid_handoff)

    try:
        workflow.run_payload(repo_root=tmp_path, run_id="invalid-handoff-run", profile="jakyeamos")
    except ValueError as error:
        assert str(error) == (
            "invalid agent handoff: agent handoff artifact_paths must be an object; "
            "agent handoff warnings must be a list of warning objects; "
            "agent handoff finding_ids must be a string list; "
            "agent handoff slice_ids must be a string list; "
            "agent handoff next_slice must be a remediation slice object; "
            "agent handoff verification_gates must be a string list"
        )
    else:
        raise AssertionError("run_payload accepted an invalid agent handoff")

    run_dir = tmp_path / ".quality-runner" / "runs" / "invalid-handoff-run"
    assert not (run_dir / "repo-scan.json").exists()
    assert not (run_dir / "standards.json").exists()
    assert not (run_dir / "capability-matrix.json").exists()
    assert not (run_dir / "agent-handoff.json").exists()
    assert not (run_dir / "quality-audit.json").exists()


def test_run_payload_reports_clean_when_no_remediation_slices(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    write_complete_js_fixture(tmp_path)

    payload = run_payload(repo_root=tmp_path, run_id="clean-run", profile="jakyeamos")
    remediation_plan = json.loads(
        Path(payload["artifact_paths"]["remediation_plan_json"]).read_text()
    )
    handoff = json.loads(Path(payload["artifact_paths"]["agent_handoff_json"]).read_text())

    assert payload["status"] == "clean"
    assert remediation_plan["slices"] == []
    assert handoff["status"] == "clean"


def test_generated_remediation_plan_orders_findings_and_exposes_actions(tmp_path: Path) -> None:
    from quality_runner.audit import build_audit_report
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.planning import build_remediation_plan
    from quality_runner.standards import compile_standards

    scan = inspect_repo(tmp_path, run_id="ordered-plan-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)
    report = build_audit_report(scan=scan, standards_packet=packet, capability_map=capability_map)

    plan = build_remediation_plan(audit_report=report, capability_map=capability_map)

    priorities = [slice_item["priority"] for slice_item in plan["slices"]]
    ids = [slice_item["findings"][0]["id"] for slice_item in plan["slices"]]
    assert priorities[:5] == ["high", "high", "high", "high", "high"]
    assert ids[:5] == [
        "missing-dead-code",
        "missing-formatter",
        "missing-lint",
        "missing-tests",
        "missing-typecheck",
    ]
    first_slice = plan["slices"][0]
    assert first_slice["actions"] == [
        "Apply recommended fix: Add a dead-code scan command such as pnpm audit:dead-code.",
        "Rerun quality-runner and confirm missing-dead-code no longer appears.",
    ]
    assert first_slice["verification_gates"] == [
        "Add the dead_code capability and rerun quality-runner.",
        "Confirm audit finding missing-dead-code is absent from the regenerated report.",
    ]
    assert first_slice["findings"] == [
        {
            "id": "missing-dead-code",
            "severity": "blocker",
            "category": "capability",
            "summary": "Required quality capability is missing: dead_code.",
        }
    ]


def test_generated_audit_report_validates(tmp_path: Path) -> None:
    from quality_runner.audit import build_audit_report
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.findings import validate_audit_report
    from quality_runner.standards import compile_standards

    scan = inspect_repo(tmp_path, run_id="audit-valid-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    report = build_audit_report(scan=scan, standards_packet=packet, capability_map=capability_map)

    assert validate_audit_report(report) == {"passed": True, "errors": []}


def test_audit_and_plan_markdown_render_findings_and_clean_states() -> None:
    from quality_runner.audit import render_audit_markdown
    from quality_runner.planning import render_handoff_markdown, render_plan_markdown

    audit_markdown = render_audit_markdown(
        {
            "schema": "quality-runner-audit-report-v0.1",
            "status": "findings",
            "implementation_allowed": False,
            "findings": [
                {
                    "id": "missing-lint",
                    "severity": "blocker",
                    "category": "capability",
                    "summary": "Required quality capability is missing: lint.",
                    "recommended_fix": "Add a lint gate.",
                    "evidence": ["Capability map lists lint as missing."],
                    "verification": ["Rerun quality-runner."],
                },
                "invalid",
            ],
        }
    )
    clean_audit_markdown = render_audit_markdown(
        {
            "schema": "quality-runner-audit-report-v0.1",
            "status": "clean",
            "implementation_allowed": False,
            "findings": [],
        }
    )
    plan_markdown = render_plan_markdown(
        {
            "schema": "quality-runner-remediation-plan-v0.1",
            "implementation_allowed": False,
            "slices": [
                {
                    "id": "remediate-missing-lint",
                    "title": "Remediate missing-lint",
                    "priority": "high",
                    "findings": [
                        {
                            "id": "missing-lint",
                            "summary": "Required quality capability is missing: lint.",
                        }
                    ],
                    "actions": ["Add a lint gate."],
                    "verification_gates": ["Rerun quality-runner."],
                },
                "invalid",
            ],
        }
    )
    clean_plan_markdown = render_plan_markdown(
        {
            "schema": "quality-runner-remediation-plan-v0.1",
            "implementation_allowed": False,
            "slices": [],
        }
    )
    handoff_markdown = render_handoff_markdown(
        {
            "schema": "quality-runner-agent-handoff-v0.1",
            "status": "planned",
            "implementation_allowed": False,
            "artifact_paths": {"quality_audit_json": "/tmp/audit.json"},
            "warnings": [
                {
                    "code": "invalid_package_json",
                    "message": "package.json could not be parsed as JSON",
                    "path": "package.json",
                },
                "invalid",
            ],
            "next_slice": {
                "id": "remediate-missing-lint",
                "title": "Remediate missing-lint",
                "priority": "high",
                "findings": [
                    {
                        "id": "missing-lint",
                        "summary": "Required quality capability is missing: lint.",
                    }
                ],
                "actions": ["Add a lint gate."],
            },
            "verification_gates": ["Rerun quality-runner."],
            "slice_ids": ["remediate-missing-lint"],
        }
    )
    clean_handoff_markdown = render_handoff_markdown(
        {
            "schema": "quality-runner-agent-handoff-v0.1",
            "status": "clean",
            "implementation_allowed": False,
            "artifact_paths": {},
            "warnings": [],
            "next_slice": None,
            "verification_gates": [],
            "slice_ids": [],
        }
    )

    assert "### missing-lint" in audit_markdown
    assert "No findings." in clean_audit_markdown
    assert "### remediate-missing-lint" in plan_markdown
    assert "No remediation slices are required." in clean_plan_markdown
    assert "invalid_package_json (package.json)" in handoff_markdown
    assert "No remediation slice is queued." in clean_handoff_markdown


def test_generated_remediation_plan_validates(tmp_path: Path) -> None:
    from quality_runner.audit import build_audit_report
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.findings import validate_remediation_plan
    from quality_runner.planning import build_remediation_plan
    from quality_runner.standards import compile_standards

    scan = inspect_repo(tmp_path, run_id="plan-valid-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)
    report = build_audit_report(scan=scan, standards_packet=packet, capability_map=capability_map)

    plan = build_remediation_plan(audit_report=report, capability_map=capability_map)

    assert validate_remediation_plan(plan) == {"passed": True, "errors": []}


def test_run_payload_only_writes_quality_runner_artifacts(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    write_js_fixture(tmp_path)
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    run_payload(repo_root=tmp_path, run_id="write-boundary-001", profile="jakyeamos")

    after = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    created = after - before
    assert created
    assert all(path.parts[0] == ".quality-runner" for path in created)
