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


def test_write_json_creates_parent_and_stable_json(tmp_path: Path) -> None:
    from quality_runner.artifacts import write_json

    path = write_json(tmp_path / "nested" / "payload.json", {"b": 2, "a": 1})

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'


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
