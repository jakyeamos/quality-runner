from __future__ import annotations

from pathlib import Path

import pytest

from quality_runner.config import load_repo_config
from quality_runner.core.audit_contracts import TextFileLimit
from quality_runner.exclusion_preflight import build_exclusion_packet
from quality_runner.scan_scope import create_text_scan_scope, discover_text_files
from quality_runner.scan_scope_reporting import scan_budget_summary
from quality_runner.security.scan import create_security_scan


def _config(root: Path, value: str) -> dict:
    (root / ".quality-runner.toml").write_text(
        f"[quality_runner.structural_scan]\nmax_text_files = {value}\n",
        encoding="utf-8",
    )
    return load_repo_config(root)


@pytest.mark.parametrize("value", ['"unlimited"', "1", "5000"])
def test_file_budget_config_accepts_explicit_unlimited_or_positive_integer(
    tmp_path: Path, value: str
) -> None:
    config = _config(tmp_path, value)

    assert config["warnings"] == []
    assert config["structural_scan"]["max_text_files"] == (
        "unlimited" if value.startswith('"') else int(value)
    )


@pytest.mark.parametrize("value", ["0", "-1", "true", "1.5", '"Unlimited"', '"0"'])
def test_invalid_file_budget_is_not_an_unlimited_alias(tmp_path: Path, value: str) -> None:
    config = _config(tmp_path, value)

    assert "max_text_files" not in config["structural_scan"]
    assert any(
        "max_text_files" in warning["message"] and '"unlimited"' in warning["message"]
        for warning in config["warnings"]
    )


def test_unlimited_shared_scope_crosses_default_and_preserves_exclusions(tmp_path: Path) -> None:
    _config(tmp_path, '"unlimited"')
    source = tmp_path / "src"
    source.mkdir()
    expected = {f"src/file-{index:04}.ts" for index in range(2501)}
    for relative in expected:
        (tmp_path / relative).write_text("// source\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.ts").write_text("eval(input);\n", encoding="utf-8")
    (source / "linked.ts").symlink_to(source / "file-0000.ts")

    scope = create_text_scan_scope(
        tmp_path, scan={}, config=None, read_files=False, cache_mode="disabled"
    )

    assert set(scope.file_paths) == expected | {".quality-runner.toml"}
    assert scan_budget_summary(
        scanned_files=len(scope.file_paths),
        max_text_files=scope.max_text_files,
        skipped_files=list(scope.skipped_files),
    ) == {
        "max_text_files": "unlimited",
        "scanned_text_files": 2502,
        "budget_exceeded": False,
        "skipped_text_files": 0,
    }
    assert any(item["path"] == "node_modules" for item in scope.skipped_files)


@pytest.mark.parametrize("limit, count", [(1, 1), (3, 3), ("unlimited", 3)])
def test_legacy_discovery_honors_finite_and_unlimited_limits(
    tmp_path: Path, limit: TextFileLimit, count: int
) -> None:
    for name in ("a.ts", "b.ts", "c.ts"):
        (tmp_path / name).write_text("// source\n", encoding="utf-8")
    skipped: list[dict[str, object]] = []

    paths = discover_text_files(
        tmp_path,
        skipped_files=skipped,
        generated_paths=set(),
        include_ignored_paths=set(),
        scan_exclusions=[],
        max_text_files=limit,
    )

    assert [path.name for path in paths] == ["a.ts", "b.ts", "c.ts"][:count]
    assert len(skipped) == 3 - count


def test_unlimited_standalone_security_scans_past_its_default(tmp_path: Path) -> None:
    config = _config(tmp_path, '"unlimited"')
    for index in range(5000):
        (tmp_path / f"file-{index:04}.js").write_text("// source\n", encoding="utf-8")
    (tmp_path / "z-sink.js").write_text("eval(userInput);\n", encoding="utf-8")

    scan = create_security_scan(tmp_path, scan={}, config=config, cache_mode="disabled")

    assert any(
        item["file"] == "z-sink.js" and item["category"] == "dangerous-sink"
        for item in scan["candidates"]
    )


def test_unlimited_preflight_retains_the_literal_budget(tmp_path: Path) -> None:
    _config(tmp_path, '"unlimited"')

    packet = build_exclusion_packet(tmp_path, "unlimited-preflight")

    assert packet["config"]["timeout_signals"]["structural_max_text_files"] == "unlimited"
