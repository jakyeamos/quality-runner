from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from quality_runner.code_quality import create_code_quality_scan


def _large_source_rules(root: Path) -> set[str]:
    result = create_code_quality_scan(
        root,
        scan={"run_id": "prevention-fixture"},
        config={
            "structural_scan": {
                "large_file_lines": 5,
                "similarity_enabled": False,
            }
        },
    )
    return {
        str(item["rule_id"])
        for item in result["findings"]
        if item.get("rule_id") == "large-source-file"
    }


def _nested_ternary_rules(root: Path) -> list[dict[str, object]]:
    result = create_code_quality_scan(
        root,
        scan={"run_id": "nested-ternary-prevention-fixture"},
        config={"structural_scan": {"similarity_enabled": False}},
    )
    return [item for item in result["findings"] if item.get("rule_id") == "nested-ternary"]


def test_large_source_file_positive_promotion_fixture(tmp_path: Path) -> None:
    source = tmp_path / "src" / "service.py"
    source.parent.mkdir()
    source.write_text("\n".join(f"value_{index} = {index}" for index in range(6)))

    assert "large-source-file" in _large_source_rules(tmp_path)


def test_large_source_file_negative_promotion_fixture(tmp_path: Path) -> None:
    source = tmp_path / "src" / "service.py"
    source.parent.mkdir()
    source.write_text("\n".join(f"value_{index} = {index}" for index in range(5)))

    assert "large-source-file" not in _large_source_rules(tmp_path)


def test_large_source_file_ambiguous_test_scope_fixture_is_not_enforced(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "test_large.py"
    source.parent.mkdir()
    source.write_text("\n".join(f"value_{index} = {index}" for index in range(6)))

    assert "large-source-file" not in _large_source_rules(tmp_path)


def test_nested_ternary_positive_promotion_fixture(tmp_path: Path) -> None:
    source = tmp_path / "src" / "decision.ts"
    source.parent.mkdir()
    source.write_text("const label = enabled ? ready ? 'ready' : 'waiting' : 'disabled';\n")

    assert len(_nested_ternary_rules(tmp_path)) == 1


def test_nested_ternary_negative_promotion_fixture(tmp_path: Path) -> None:
    source = tmp_path / "src" / "decision.ts"
    source.parent.mkdir()
    source.write_text("const label = enabled ? 'enabled' : 'disabled';\n")

    assert _nested_ternary_rules(tmp_path) == []


def test_nested_ternary_ambiguous_syntax_fixture_is_not_enforced(tmp_path: Path) -> None:
    source = tmp_path / "src" / "syntax.ts"
    source.parent.mkdir()
    source.write_text(
        "\n".join(
            [
                "const name = input?.profile?.name ?? 'Unknown';",
                "const matcher = /^(?:open|closed)$/;",
                "type Optional<T> = { value?: T };",
            ]
        )
    )

    assert _nested_ternary_rules(tmp_path) == []


def test_large_source_file_occurrence_fingerprint_is_stable_across_line_growth(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "service.py"
    source.parent.mkdir()
    source.write_text("\n".join(f"value_{index} = {index}" for index in range(6)))
    before = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "before"},
        config={"structural_scan": {"large_file_lines": 5, "similarity_enabled": False}},
    )
    source.write_text("\n".join(f"value_{index} = {index}" for index in range(8)))
    after = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "after"},
        config={"structural_scan": {"large_file_lines": 5, "similarity_enabled": False}},
    )

    before_row = next(item for item in before["findings"] if item["rule_id"] == "large-source-file")
    after_row = next(item for item in after["findings"] if item["rule_id"] == "large-source-file")
    assert before_row["fingerprint"] == after_row["fingerprint"]


@pytest.mark.parametrize(
    ("gate", "passing_source", "failing_source"),
    [
        (
            "ruff-lint",
            "value = 1\n",
            "import os\nvalue = 1\n",
        ),
        (
            "ruff-format",
            "value = [\n    1,\n    2,\n]\n",
            "value=[1,2]\n",
        ),
        (
            "basedpyright",
            "value: str = 'ok'\n",
            "value: str = 1\n",
        ),
    ],
)
def test_static_gate_certification_has_repeatable_pass_and_failure_fixture(
    tmp_path: Path,
    gate: str,
    passing_source: str,
    failing_source: str,
) -> None:
    source = tmp_path / "fixture.py"
    source.write_text(passing_source)
    command = {
        "ruff-lint": ["ruff", "check", str(source)],
        "ruff-format": ["ruff", "format", "--check", str(source)],
        "basedpyright": ["basedpyright", str(source)],
    }[gate]

    assert _run(command, tmp_path) == 0
    assert _run(command, tmp_path) == 0
    source.write_text(failing_source)
    assert _run(command, tmp_path) != 0


def test_pytest_gate_certification_has_repeatable_pass_and_failure_fixture(
    tmp_path: Path,
) -> None:
    test_file = tmp_path / "test_fixture.py"
    test_file.write_text("def test_fixture():\n    assert True\n")
    command = [sys.executable, "-m", "pytest", "-q", str(test_file)]

    assert _run(command, tmp_path) == 0
    assert _run(command, tmp_path) == 0
    test_file.write_text("def test_fixture():\n    assert False\n")
    assert _run(command, tmp_path) != 0


def _run(command: list[str], cwd: Path) -> int:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    ).returncode
