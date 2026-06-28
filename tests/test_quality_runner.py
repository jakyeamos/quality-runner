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
    assert result["errors"] == ["audit report findings must be a list"]


def test_validate_audit_report_rejects_non_list_findings() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report({"findings": "not-a-list"})

    assert result["passed"] is False
    assert result["errors"] == ["audit report findings must be a list"]


def test_validate_audit_report_rejects_non_dict_findings() -> None:
    from quality_runner.findings import validate_audit_report

    result = validate_audit_report({"findings": ["not-a-dict"]})

    assert result["passed"] is False
    assert result["errors"] == ["finding at index 0 is not an object"]


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
    assert result["errors"] == ["remediation plan slices must be a list"]


def test_validate_remediation_plan_rejects_non_list_slices() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan({"slices": "not-a-list"})

    assert result["passed"] is False
    assert result["errors"] == ["remediation plan slices must be a list"]


def test_validate_remediation_plan_rejects_non_dict_slices() -> None:
    from quality_runner.findings import validate_remediation_plan

    result = validate_remediation_plan({"slices": ["not-a-dict"]})

    assert result["passed"] is False
    assert result["errors"] == ["slice at index 0 is not an object"]
