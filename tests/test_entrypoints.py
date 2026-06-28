from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

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


def test_module_entrypoint_rejects_unknown_commands() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "quality_runner", "audit", "/tmp", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "invalid choice: 'audit'" in result.stderr


def test_scaffold_entrypoint_functions_import_and_return_success() -> None:
    sys.path.insert(0, str(ROOT))

    from quality_runner.cli import main as cli_main
    from quality_runner.mcp import main as mcp_main

    assert cli_main(["--version"]) == 0
    assert cli_main(["audit"]) == 2
    assert mcp_main(["--version"]) == 0
    assert mcp_main() == 2


def test_packaged_console_script_invokes_cli(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    try:
        subprocess.run(
            [
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
            ],
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
        entry_points = wheel.read("quality_runner-0.1.0.dist-info/entry_points.txt").decode()
    assert "quality-runner = quality_runner.cli:main" in entry_points
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
    doctor_result = subprocess.run(
        [str(quality_runner), "doctor", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert version_result.stdout.strip() == "0.1.0"
    doctor_payload = json.loads(doctor_result.stdout)
    assert doctor_payload["schema"] == "quality-runner-doctor-result-v0.1"
    assert doctor_payload["status"] == "ready"
