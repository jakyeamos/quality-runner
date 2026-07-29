from __future__ import annotations

import importlib.util
from pathlib import Path


def test_lcov_writer_counts_executable_lines_only(tmp_path: Path, monkeypatch) -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_pytest_with_lcov.py"
    spec = importlib.util.spec_from_file_location("run_pytest_with_lcov", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    package_root = tmp_path / "quality_runner"
    package_root.mkdir()
    source_file = package_root / "sample.py"
    source_file.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "VALUE = 1",
                "",
                "def add_one(value: int) -> int:",
                "    return value + 1",
                "",
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "coverage.lcov"
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "PACKAGE_ROOT", package_root)
    monkeypatch.setattr(module, "OUTPUT", output)

    module.write_lcov({(str(source_file), 3): 1, (str(source_file), 6): 1})

    lcov = output.read_text(encoding="utf-8")
    assert "SF:quality_runner/sample.py" in lcov
    assert "DA:3,1" in lcov
    assert "DA:5,0" in lcov
    assert "DA:6,1" in lcov
    assert "LF:4" in lcov
    assert "LH:2" in lcov


def test_lcov_writer_includes_nested_package_modules(tmp_path: Path, monkeypatch) -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_pytest_with_lcov.py"
    spec = importlib.util.spec_from_file_location("run_pytest_with_lcov_nested", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    package_root = tmp_path / "quality_runner"
    nested_root = package_root / "security"
    nested_root.mkdir(parents=True)
    source_file = nested_root / "audit.py"
    source_file.write_text("def audit() -> bool:\n    return True\n", encoding="utf-8")
    output = tmp_path / "coverage.lcov"
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "PACKAGE_ROOT", package_root)
    monkeypatch.setattr(module, "OUTPUT", output)

    module.write_lcov({(str(source_file), 2): 1})

    lcov = output.read_text(encoding="utf-8")
    assert "SF:quality_runner/security/audit.py" in lcov
    assert "DA:2,1" in lcov


def test_changed_only_selects_staged_tests(tmp_path: Path, monkeypatch) -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_pytest_with_lcov.py"
    spec = importlib.util.spec_from_file_location("run_pytest_with_lcov_changed", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Result", (), {"returncode": 0, "stdout": "quality_runner/config.py\n"}
        )(),
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_config.py").write_text("", encoding="utf-8")

    assert module.build_pytest_args(["--changed-only", "--ignore", "tests/test_entrypoints.py"]) == [
        "-q",
        "--ignore",
        "tests/test_entrypoints.py",
        "tests/test_config.py",
    ]
