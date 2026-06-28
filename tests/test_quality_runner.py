from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_package_imports_without_aios() -> None:
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(ROOT)!r}); "
        "import quality_runner; "
        "print(quality_runner.__version__)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "0.1.0"


def test_module_entrypoint_exits_successfully() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Quality Runner" in result.stdout


def test_module_entrypoint_version_exits_successfully() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "0.1.0"


def test_module_entrypoint_fails_closed_for_pending_commands() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "audit", "/tmp", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "not implemented" in result.stderr


def test_scaffold_entrypoint_functions_import_and_return_success() -> None:
    sys.path.insert(0, str(ROOT))

    from quality_runner.cli import main as cli_main
    from quality_runner.mcp import main as mcp_main

    assert cli_main(["--version"]) == 0
    assert cli_main(["audit"]) == 2
    assert mcp_main(["--version"]) == 0
    assert mcp_main() == 2


def test_artifact_dir_uses_quality_runner_namespace(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    path = artifact_dir(tmp_path, "run-001")

    assert path == tmp_path / ".quality-runner" / "runs" / "run-001"


def test_artifact_dir_rejects_absolute_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "/tmp/run-001")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted an absolute run ID")


def test_artifact_dir_rejects_parent_traversal_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "../escape")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a parent traversal run ID")


def test_artifact_dir_rejects_empty_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted an empty run ID")


def test_artifact_dir_rejects_separator_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "nested/run")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a separator run ID")


def test_artifact_dir_rejects_backslash_separator_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "nested\\run")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a backslash separator run ID")


def test_artifact_dir_rejects_windows_absolute_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "C:\\temp\\run")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a Windows absolute run ID")


def test_artifact_dir_rejects_windows_drive_relative_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "C:run")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a Windows drive-relative run ID")


def test_artifact_dir_rejects_dot_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, ".")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a dot run ID")


def test_artifact_dir_rejects_parent_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "..")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a parent run ID")


def test_write_json_creates_parent_and_stable_json(tmp_path: Path) -> None:
    from quality_runner.artifacts import write_json

    path = write_json(tmp_path / "nested" / "payload.json", {"b": 2, "a": 1})

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'


def test_write_text_creates_parent_returns_path_and_writes_exact_content(tmp_path: Path) -> None:
    from quality_runner.artifacts import write_text

    target = tmp_path / "nested" / "report.txt"
    path = write_text(target, "line 1\nline 2")

    assert path == target
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "line 1\nline 2"


def _write_js_fixture(repo: Path) -> None:
    (repo / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                    "test": "vitest run",
                    "build": "vite build",
                    "dead-code": "knip",
                    "pre-cr": "pre-cr",
                }
            }
        ),
        encoding="utf-8",
    )
    (repo / "AGENTS.md").write_text(
        "Always use pnpm. Full lint, typecheck, tests, and dead-code scans are required.\n",
        encoding="utf-8",
    )
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (repo / ".pre-cr.json").write_text("{}", encoding="utf-8")
    (repo / ".tracker").mkdir()
    (repo / ".tracker" / "PROJECT_TRUTH.md").write_text(
        "---\nprojectName: Fixture\n---\n",
        encoding="utf-8",
    )


def test_inspect_repo_detects_js_quality_surfaces(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    _write_js_fixture(tmp_path)

    scan = inspect_repo(tmp_path, run_id="scan-001")

    assert scan["schema"] == "quality-runner-repo-scan-v0.1"
    assert scan["package_manager"] == "pnpm"
    assert scan["languages"] == ["javascript"]
    assert scan["scripts"]["lint"] == "eslint ."
    assert scan["pre_cr_config"] == ".pre-cr.json"
    assert scan["truth_file"] == ".tracker/PROJECT_TRUTH.md"


def test_inspect_repo_does_not_infer_package_manager_from_policy_text(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text("Always use pnpm.\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="policy-only-001")

    assert scan["package_manager"] is None


def test_compile_standards_does_not_warn_for_unknown_package_manager(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="unknown-package-manager-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")

    assert scan["package_manager"] is None
    requirement_ids = {requirement["id"] for requirement in packet["requirements"]}
    assert "package_manager_mismatch" not in requirement_ids


def test_inspect_repo_does_not_mark_tests_required_from_latest(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "AGENTS.md").write_text("Use the latest stable toolchain.\n", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="latest-001")

    assert scan["quality_contract"]["required_terms"]["tests"] is False


def test_inspect_repo_warns_on_invalid_package_json(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    (tmp_path / "package.json").write_text("{not-json", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="invalid-package-001")

    assert scan["scripts"] == {}
    assert scan["warnings"] == [
        {
            "code": "invalid_package_json",
            "message": "package.json could not be parsed as JSON",
            "path": "package.json",
        }
    ]


def test_package_json_warnings_propagate_to_standards_and_capabilities(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text("{not-json", encoding="utf-8")

    scan = inspect_repo(tmp_path, run_id="invalid-package-002")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")
    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    expected_warning = {
        "code": "invalid_package_json",
        "message": "package.json could not be parsed as JSON",
        "path": "package.json",
    }
    assert expected_warning in packet["warnings"]
    assert expected_warning in capability_map["warnings"]


def test_inspect_repo_expands_home_before_validating(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from quality_runner.discovery import inspect_repo

    home = tmp_path / "home"
    repo = home / "repo"
    repo.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    scan = inspect_repo(Path("~/repo"), run_id="home-001")

    assert scan["repo_root"] == str(repo.resolve())


def test_inspect_repo_rejects_missing_repo_root(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    missing_root = tmp_path / "missing"

    try:
        inspect_repo(missing_root, run_id="missing-001")
    except FileNotFoundError as error:
        assert str(error) == f"repo root does not exist: {missing_root}"
    else:
        raise AssertionError("inspect_repo accepted a missing repo root")


def test_inspect_repo_rejects_file_repo_root(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo

    file_root = tmp_path / "not-a-directory"
    file_root.write_text("content", encoding="utf-8")

    try:
        inspect_repo(file_root, run_id="file-001")
    except NotADirectoryError as error:
        assert str(error) == f"repo root is not a directory: {file_root}"
    else:
        raise AssertionError("inspect_repo accepted a file repo root")


def test_compile_standards_preserves_profile_and_local_provenance(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    _write_js_fixture(tmp_path)
    scan = inspect_repo(tmp_path, run_id="scan-001")

    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")

    assert packet["schema"] == "quality-runner-standards-packet-v0.1"
    assert packet["profile"] == "jakyeamos"
    sources = {source["path"] for source in packet["sources"]}
    assert "AGENTS.md" in sources
    requirement_ids = {requirement["id"] for requirement in packet["requirements"]}
    assert "use_pnpm" in requirement_ids
    assert "truth_file_current" in requirement_ids


def test_compile_standards_rejects_unsupported_profiles(tmp_path: Path) -> None:
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    scan = inspect_repo(tmp_path, run_id="scan-001")

    try:
        compile_standards(repo_root=tmp_path, scan=scan, profile="someone-else")
    except ValueError as error:
        assert str(error) == "unsupported standards profile: someone-else"
    else:
        raise AssertionError("compile_standards accepted an unsupported profile")


def test_compile_standards_handles_malformed_package_manager() -> None:
    from quality_runner.standards import compile_standards

    packet = compile_standards(
        repo_root=Path("/tmp"),
        scan={"package_manager": []},
        profile="jakyeamos",
    )

    assert {
        "code": "invalid_package_manager",
        "message": "scan package_manager must be a string or null",
        "path": "package_manager",
    } in packet["warnings"]
    requirement_ids = {requirement["id"] for requirement in packet["requirements"]}
    assert "package_manager_mismatch" in requirement_ids


def test_detect_capabilities_includes_standards_warnings() -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.standards import compile_standards

    scan = {"package_manager": []}
    packet = compile_standards(repo_root=Path("/tmp"), scan=scan, profile="jakyeamos")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert {
        "code": "invalid_package_manager",
        "message": "scan package_manager must be a string or null",
        "path": "package_manager",
    } in capability_map["warnings"]


def test_detect_capabilities_records_missing_expected_surfaces(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    scan = inspect_repo(tmp_path, run_id="empty-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    assert capability_map["schema"] == "quality-runner-capability-map-v0.1"
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "lint" in missing_ids
    assert "tests" in missing_ids
    assert "truth_file" in missing_ids


def test_detect_capabilities_records_pre_cr_script_with_stable_id(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"pre-cr": "pre-cr"}}),
        encoding="utf-8",
    )
    scan = inspect_repo(tmp_path, run_id="pre-cr-script-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    available_ids = {item["id"] for item in capability_map["available"]}
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "pre_cr" in available_ids
    assert "pre_cr" not in missing_ids
    assert "pre_pr" in missing_ids


def test_detect_capabilities_records_pre_cr_config_with_stable_id(tmp_path: Path) -> None:
    from quality_runner.capabilities import detect_capabilities
    from quality_runner.discovery import inspect_repo
    from quality_runner.standards import compile_standards

    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / ".pre-cr.json").write_text("{}", encoding="utf-8")
    scan = inspect_repo(tmp_path, run_id="pre-cr-config-001")
    packet = compile_standards(repo_root=tmp_path, scan=scan, profile="jakyeamos")

    capability_map = detect_capabilities(scan=scan, standards_packet=packet)

    available_ids = {item["id"] for item in capability_map["available"]}
    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "pre_cr" in available_ids
    assert "pre_cr" not in missing_ids


def test_detect_capabilities_treats_malformed_scripts_as_missing() -> None:
    from quality_runner.capabilities import detect_capabilities

    capability_map = detect_capabilities(
        scan={"schema": "quality-runner-repo-scan-v0.1", "scripts": "not-a-dict"},
        standards_packet={"profile": "jakyeamos"},
    )

    missing_ids = {item["id"] for item in capability_map["missing"]}
    assert "lint" in missing_ids
    assert "tests" in missing_ids


def test_validate_audit_report_rejects_findings_without_evidence() -> None:
    from quality_runner.findings import validate_audit_report

    report = {
        "schema": "quality-runner-audit-report-v0.1",
        "findings": [
            {
                "id": "missing-evidence",
                "severity": "warning",
                "category": "docs",
                "summary": "No evidence",
                "evidence": [],
                "recommended_fix": "Add evidence",
                "verification": ["review report"],
            }
        ],
    }

    result = validate_audit_report(report)

    assert result["passed"] is False
    assert result["errors"] == ["finding missing-evidence has no evidence"]


def test_validate_audit_report_rejects_missing_schema() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report({"findings": []})

    assert result["passed"] is False
    assert result["errors"] == ["audit report schema must be quality-runner-audit-report-v0.1"]


def test_validate_audit_report_rejects_missing_required_finding_fields() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report(
        {
            "schema": "quality-runner-audit-report-v0.1",
            "findings": [{"evidence": ["line 1"]}],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == [
        "finding at index 0 field id must be a non-empty string",
        "finding at index 0 field severity must be a non-empty string",
        "finding at index 0 field category must be a non-empty string",
        "finding at index 0 field summary must be a non-empty string",
        "finding at index 0 field recommended_fix must be a non-empty string",
        "finding unknown has no verification",
    ]


def test_validate_audit_report_rejects_missing_findings() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report({})

    assert result["passed"] is False
    assert result["errors"] == [
        "audit report schema must be quality-runner-audit-report-v0.1",
        "audit report findings must be a list",
    ]


def test_validate_audit_report_rejects_non_list_findings() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report({"findings": "not-a-list"})

    assert result["passed"] is False
    assert result["errors"] == [
        "audit report schema must be quality-runner-audit-report-v0.1",
        "audit report findings must be a list",
    ]


def test_validate_audit_report_rejects_non_dict_findings() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report({"schema": "wrong", "findings": ["not-a-dict"]})

    assert result["passed"] is False
    assert result["errors"] == [
        "audit report schema must be quality-runner-audit-report-v0.1",
        "finding at index 0 is not an object",
    ]


def test_validate_audit_report_rejects_non_string_evidence_items() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report(
        {
            "schema": "quality-runner-audit-report-v0.1",
            "findings": [
                {
                    "id": "finding-001",
                    "severity": "warning",
                    "category": "docs",
                    "summary": "Bad evidence",
                    "evidence": [123],
                    "recommended_fix": "Use string evidence",
                    "verification": ["review report"],
                }
            ],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == ["finding finding-001 has no evidence"]


def test_validate_audit_report_rejects_empty_string_verification_items() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report(
        {
            "schema": "quality-runner-audit-report-v0.1",
            "findings": [
                {
                    "id": "finding-001",
                    "severity": "warning",
                    "category": "docs",
                    "summary": "Bad verification",
                    "evidence": ["line 1"],
                    "recommended_fix": "Use string verification",
                    "verification": [""],
                }
            ],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == ["finding finding-001 has no verification"]


def test_validate_remediation_plan_rejects_slices_without_verification() -> None:
    from quality_runner.findings import validate_remediation_plan

    plan = {
        "schema": "quality-runner-remediation-plan-v0.1",
        "slices": [
            {
                "id": "slice-001",
                "title": "No verification",
                "findings": ["finding-001"],
                "verification": [],
            }
        ],
    }

    result = validate_remediation_plan(plan)

    assert result["passed"] is False
    assert result["errors"] == ["slice slice-001 has no verification"]


def test_validate_remediation_plan_rejects_missing_schema() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan({"slices": []})

    assert result["passed"] is False
    assert result["errors"] == [
        "remediation plan schema must be quality-runner-remediation-plan-v0.1"
    ]


def test_validate_remediation_plan_rejects_missing_required_slice_fields() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan(
        {
            "schema": "quality-runner-remediation-plan-v0.1",
            "slices": [{"verification": ["run tests"]}],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == [
        "slice at index 0 field id must be a non-empty string",
        "slice at index 0 field title must be a non-empty string",
        "slice unknown has no findings",
    ]


def test_validate_remediation_plan_rejects_missing_slices() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan({})

    assert result["passed"] is False
    assert result["errors"] == [
        "remediation plan schema must be quality-runner-remediation-plan-v0.1",
        "remediation plan slices must be a list",
    ]


def test_validate_remediation_plan_rejects_non_list_slices() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan({"slices": "not-a-list"})

    assert result["passed"] is False
    assert result["errors"] == [
        "remediation plan schema must be quality-runner-remediation-plan-v0.1",
        "remediation plan slices must be a list",
    ]


def test_validate_remediation_plan_rejects_non_dict_slices() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan({"schema": "wrong", "slices": ["not-a-dict"]})

    assert result["passed"] is False
    assert result["errors"] == [
        "remediation plan schema must be quality-runner-remediation-plan-v0.1",
        "slice at index 0 is not an object",
    ]


def test_validate_remediation_plan_rejects_non_string_finding_items() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan(
        {
            "schema": "quality-runner-remediation-plan-v0.1",
            "slices": [
                {
                    "id": "slice-001",
                    "title": "Bad findings",
                    "findings": [None],
                    "verification": ["run tests"],
                }
            ],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == ["slice slice-001 has no findings"]


def test_validate_remediation_plan_rejects_non_string_verification_items() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan(
        {
            "schema": "quality-runner-remediation-plan-v0.1",
            "slices": [
                {
                    "id": "slice-001",
                    "title": "Bad verification",
                    "findings": ["finding-001"],
                    "verification": [123],
                }
            ],
        }
    )

    assert result["passed"] is False
    assert result["errors"] == ["slice slice-001 has no verification"]


def test_run_payload_writes_audit_plan_and_handoff(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    _write_js_fixture(tmp_path)

    payload = run_payload(repo_root=tmp_path, run_id="run-001", profile="jakyeamos")

    assert payload["schema"] == "quality-runner-run-result-v0.1"
    assert payload["status"] == "planned"
    assert payload["implementation_allowed"] is False
    artifact_paths = payload["artifact_paths"]
    assert Path(artifact_paths["repo_scan_json"]).exists()
    assert Path(artifact_paths["standards_packet_json"]).exists()
    assert Path(artifact_paths["capability_map_json"]).exists()
    assert Path(artifact_paths["audit_report_json"]).exists()
    assert Path(artifact_paths["remediation_plan_json"]).exists()
    assert Path(artifact_paths["agent_handoff_md"]).exists()


def test_run_payload_records_missing_capability_findings(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    payload = run_payload(repo_root=tmp_path, run_id="empty-run", profile="jakyeamos")
    audit_report = json.loads(Path(payload["artifact_paths"]["audit_report_json"]).read_text())

    finding_ids = {finding["id"] for finding in audit_report["findings"]}
    assert "missing-lint" in finding_ids
    assert "missing-tests" in finding_ids
    assert "missing-truth-file" in finding_ids


def test_inspect_payload_does_not_write_audit_plan(tmp_path: Path) -> None:
    from quality_runner.workflow import inspect_payload

    payload = inspect_payload(repo_root=tmp_path, run_id="inspect-001", profile="jakyeamos")

    assert payload["schema"] == "quality-runner-inspect-result-v0.1"
    assert Path(payload["artifact_paths"]["repo_scan_json"]).exists()
    assert "audit_report_json" not in payload["artifact_paths"]


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

    _write_js_fixture(tmp_path)
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    run_payload(repo_root=tmp_path, run_id="write-boundary-001", profile="jakyeamos")

    after = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}
    created = after - before
    assert created
    assert all(path.parts[0] == ".quality-runner" for path in created)
