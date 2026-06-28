from __future__ import annotations

import subprocess
import sys
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


def test_scaffold_entrypoint_functions_import_and_return_success() -> None:
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(ROOT)!r}); "
        "from quality_runner.cli import main as cli_main; "
        "from quality_runner.mcp import main as mcp_main; "
        "print(cli_main(['--version']), mcp_main())"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines()[-1] == "0 0"
