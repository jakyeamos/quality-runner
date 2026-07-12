from __future__ import annotations

import json
import runpy
import shutil
import subprocess
import sys
import zipfile
from email.parser import BytesParser
from pathlib import Path

from quality_runner import __version__

ROOT = Path(__file__).resolve().parents[1]


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

    assert result.stdout.strip() == __version__


def test_module_entrypoint_exits_successfully() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Quality Runner" in result.stdout


def test_module_entrypoint_runs_in_process(capsys, monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["quality-runner"])

    try:
        runpy.run_module("quality_runner.__main__", run_name="__main__")
    except SystemExit as error:
        assert error.code == 0
    else:
        raise AssertionError("__main__ did not raise SystemExit")

    assert "Quality Runner" in capsys.readouterr().out


def test_module_entrypoint_version_exits_successfully() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "--version"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == __version__


def test_module_entrypoint_rejects_unknown_commands() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "unknown-command", "/tmp", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "invalid choice: 'unknown-command'" in result.stderr


def test_scaffold_entrypoint_functions_import_and_return_success(monkeypatch) -> None:
    sys.path.insert(0, str(ROOT))

    from quality_runner.cli import main as cli_main
    from quality_runner.mcp import main as mcp_main

    assert cli_main(["--version"]) == 0
    assert cli_main(["unknown-command"]) == 2
    assert mcp_main(["--version"]) == 0
    monkeypatch.setattr("sys.stdin", iter([]))
    assert mcp_main([]) == 0


def test_packaged_console_script_invokes_cli(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    build_command = [
        "uv",
        "run",
        "--offline",
        "--with",
        "setuptools",
        "--with",
        "wheel",
        "uv",
        "build",
        "--wheel",
        "--no-build-isolation",
        "--out-dir",
        str(dist_dir),
    ]
    try:
        result = subprocess.run(
            build_command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            online_command = [part for part in build_command if part != "--offline"]
            subprocess.run(
                online_command,
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
    finally:
        shutil.rmtree(ROOT / "build", ignore_errors=True)
        shutil.rmtree(ROOT / "quality_runner.egg-info", ignore_errors=True)
    wheel_path = next(dist_dir.glob("quality_runner-*.whl"))

    with zipfile.ZipFile(wheel_path) as wheel:
        wheel_names = wheel.namelist()
        metadata_path = next(name for name in wheel_names if name.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(wheel.read(metadata_path))
        dist_info_dir = metadata_path.removesuffix("/METADATA")
        entry_points = wheel.read(f"{dist_info_dir}/entry_points.txt").decode()
        plugin_manifest = json.loads(wheel.read("quality_runner/plugin/manifest.json"))
    assert metadata["Name"] == "quality-runner"
    assert metadata["Version"] == __version__
    assert plugin_manifest["version"] == __version__
    assert "quality-runner = quality_runner.cli:main" in entry_points
    assert "quality-runner-mcp = quality_runner.mcp:main" in entry_points
    assert "repo-quality-certifier = repo_quality_certifier.cli:main" in entry_points
    assert "repo-quality-certifier-mcp = repo_quality_certifier.mcp:main" in entry_points
    assert "quality_runner/plugin/manifest.json" in wheel_names
    assert "quality_runner/plugin/SKILL.md" in wheel_names
    assert "quality_runner/core/audit_contracts.py" in wheel_names
    assert "quality_runner/core/outcome_contracts.py" in wheel_names
    assert "quality_runner/core/review_contracts.py" in wheel_names
    assert "quality_runner/application/audit_v1_artifacts.py" in wheel_names
    assert "quality_runner/application/outcome_projection.py" in wheel_names
    assert "quality_runner/application/outcome_projection_support.py" in wheel_names
    assert "quality_runner/application/read_only_audit.py" in wheel_names
    assert "quality_runner/application/review_v1_reports.py" in wheel_names
    assert "quality_runner/application/review_v1_serializers.py" in wheel_names
    assert "quality_runner/application/run_history.py" in wheel_names
    assert "quality_runner/compatibility/journey_outcomes.py" in wheel_names
    assert "quality_runner/mcp_journeys.py" in wheel_names
    assert "quality_runner/review_types.py" in wheel_names
    assert "quality_runner/scan_scope.py" in wheel_names
    assert "quality_runner/security_surface_paths.py" in wheel_names
    assert "repo_quality_certifier/plugin/manifest.json" in wheel_names
    assert "repo_quality_certifier/plugin/SKILL.md" in wheel_names
    assert not any(name.startswith("test_support/") for name in wheel_names)

    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    venv_python = venv_dir / "bin" / "python"
    subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--no-deps", str(wheel_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    quality_runner = venv_dir / "bin" / "quality-runner"
    version_result = subprocess.run(
        [str(quality_runner), "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata_version_result = subprocess.run(
        [
            str(venv_python),
            "-c",
            "from importlib.metadata import version; print(version('quality-runner'))",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    doctor_result = subprocess.run(
        [str(quality_runner), "doctor", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    smoke_result = subprocess.run(
        [
            str(quality_runner),
            "release-smoke",
            "--work-dir",
            str(tmp_path / "installed-release-smoke"),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    compat_import_result = subprocess.run(
        [
            str(venv_python),
            "-c",
            "from quality_evidence_contract import QUALITY_FINDING_SCHEMA; "
            "from repo_quality_certifier import GATE_MATRIX_SCHEMA; "
            "from quality_runner.application.review_v1_serializers import REVIEW_CONTEXT_SCHEMA; "
            "from quality_runner.review_types import ReviewPacket; "
            "print(QUALITY_FINDING_SCHEMA, GATE_MATRIX_SCHEMA, REVIEW_CONTEXT_SCHEMA)",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    repo_quality_certifier = venv_dir / "bin" / "repo-quality-certifier"
    certifier_result = subprocess.run(
        [
            str(repo_quality_certifier),
            "plan",
            "--repo-root",
            str(ROOT / "fixtures" / "corpus" / "complete-js"),
            "--run-id",
            "installed-certifier-smoke",
            "--output-dir",
            str(tmp_path / "installed-certifier-smoke"),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    certifier_mcp = venv_dir / "bin" / "repo-quality-certifier-mcp"
    mcp_result = subprocess.run(
        [str(certifier_mcp)],
        input='{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n',
        check=True,
        capture_output=True,
        text=True,
    )

    assert version_result.stdout.strip() == __version__
    doctor_payload = json.loads(doctor_result.stdout)
    assert doctor_payload["schema"] == "quality-runner-doctor-result-v0.1"
    assert doctor_payload["status"] == "ready"
    assert doctor_payload["version"] == __version__
    assert metadata_version_result.stdout.strip() == __version__
    smoke_payload = json.loads(smoke_result.stdout)
    assert smoke_payload["schema"] == "quality-runner-release-smoke-result-v0.1"
    assert smoke_payload["status"] == "passed"
    assert Path(smoke_payload["handoff_output"]).exists()
    assert compat_import_result.stdout.strip() == (
        "quality-finding-v0.1 aios-repo-gate-matrix-v0.1 quality-runner-review-context-v0.1"
    )
    certifier_payload = json.loads(certifier_result.stdout)
    assert certifier_payload["schema"] == "repo-quality-certifier-plan-result-v0.1"
    assert Path(certifier_payload["artifact_paths"]["gate_matrix_json"]).exists()
    mcp_payload = json.loads(mcp_result.stdout)
    assert {tool["name"] for tool in mcp_payload["result"]["tools"]} == {
        "repo_quality_certifier_plan",
        "repo_quality_certifier_doc_quality",
    }
