from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _policy(**overrides: object) -> dict[str, object]:
    base = {
        "similarity_enabled": True,
        "similarity_threshold": 0.87,
        "similarity_min_lines": 8,
        "similarity_max_pairs": 25,
        "similarity_timeout_seconds": 30,
        "similarity_include_tests": False,
    }
    base.update(overrides)
    return base


PAIR_OUTPUT = """\
Similarity: 92.50%, Score: 18.5 points (lines 10~12, avg: 11.0)
  src/foo.ts:10-21 parseFoo
  src/bar.ts:40-51 parseBar
"""

CLUSTER_OUTPUT = """\
Cluster 1: 3 functions, 3 pairwise matches, avg similarity 91.00%, best score 20.0
  src/foo.ts:10-21 parseFoo
  src/bar.ts:40-51 parseBar
  src/baz.ts:80-91 parseBaz
"""

PYTHON_OUTPUT = """\
Duplicates in src/foo.py:
------------------------------------------------------------
  src/foo.py:10 | L10-20 function parse_foo <-> src/foo.py:40 | L40-50 function parse_bar
  Similarity: 90.00%
"""


def test_missing_similarity_tools_do_not_fail_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")
    monkeypatch.setattr("quality_runner.code_quality_similarity.shutil.which", lambda _: None)

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    assert result["summary"]["semantic_similarity_clusters"] == 0
    assert result["summary"]["semantic_similarity_tools"] == {"similarity-ts": "missing"}


def test_similarity_ts_pair_output_creates_pair_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.code_quality_similarity import semantic_similarity_scan

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.ts").write_text("export function parseFoo() {}\n", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/similarity-ts" if name == "similarity-ts" else None

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, PAIR_OUTPUT, "")

    monkeypatch.setattr("quality_runner.code_quality_similarity.shutil.which", fake_which)
    monkeypatch.setattr("quality_runner.code_quality_similarity.subprocess.run", fake_run)

    result = semantic_similarity_scan(tmp_path, policy=_policy(), disabled_groups=set())

    assert len(result["clusters"]) == 1
    assert result["clusters"][0]["id"] == "SIM-001"
    assert result["clusters"][0]["source"] == "similarity-ts"
    assert result["findings"][0]["rule_id"] == "semantic-similarity-pair"
    assert "92.50%" in result["findings"][0]["evidence"]


def test_cluster_output_creates_cluster_and_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.code_quality_similarity import semantic_similarity_scan

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.ts").write_text("export function parseFoo() {}\n", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/similarity-ts" if name == "similarity-ts" else None

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, CLUSTER_OUTPUT, "")

    monkeypatch.setattr("quality_runner.code_quality_similarity.shutil.which", fake_which)
    monkeypatch.setattr("quality_runner.code_quality_similarity.subprocess.run", fake_run)

    result = semantic_similarity_scan(tmp_path, policy=_policy(), disabled_groups=set())

    assert len(result["clusters"]) == 1
    assert len(result["clusters"][0]["candidates"]) == 3
    assert result["findings"][0]["rule_id"] == "semantic-similarity-cluster"


def test_test_files_skipped_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quality_runner.code_quality_similarity import semantic_similarity_scan

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.test.ts").write_text("test('x', () => {});\n", encoding="utf-8")
    output = """\
Similarity: 95.00%, Score: 20.0 points
  src/foo.test.ts:1-5 parseFoo
  src/bar.test.ts:1-5 parseBar
"""

    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/similarity-ts" if name == "similarity-ts" else None

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr("quality_runner.code_quality_similarity.shutil.which", fake_which)
    monkeypatch.setattr("quality_runner.code_quality_similarity.subprocess.run", fake_run)

    result = semantic_similarity_scan(tmp_path, policy=_policy(), disabled_groups=set())

    assert result["clusters"] == []
    assert result["findings"] == []


def test_test_files_included_when_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quality_runner.code_quality_similarity import semantic_similarity_scan

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.test.ts").write_text("test('x', () => {});\n", encoding="utf-8")
    output = """\
Similarity: 95.00%, Score: 20.0 points
  src/foo.test.ts:1-5 parseFoo
  src/bar.test.ts:1-5 parseBar
"""

    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/similarity-ts" if name == "similarity-ts" else None

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr("quality_runner.code_quality_similarity.shutil.which", fake_which)
    monkeypatch.setattr("quality_runner.code_quality_similarity.subprocess.run", fake_run)

    result = semantic_similarity_scan(
        tmp_path,
        policy=_policy(similarity_include_tests=True),
        disabled_groups=set(),
    )

    assert len(result["clusters"]) == 1


def test_disabled_deduplicate_group_prevents_similarity_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.code_quality_similarity import semantic_similarity_scan

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")
    run = MagicMock()
    monkeypatch.setattr("quality_runner.code_quality_similarity.subprocess.run", run)

    result = semantic_similarity_scan(tmp_path, policy=_policy(), disabled_groups={"deduplicate"})

    run.assert_not_called()
    assert result["scanner_status"][0]["status"] == "skipped"


def test_invalid_config_values_warn_and_fallback(tmp_path: Path) -> None:
    from quality_runner.config import load_repo_config

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.structural_scan]",
                "similarity_threshold = 2.0",
                "similarity_min_lines = 0",
                "similarity_max_pairs = -1",
                "similarity_timeout_seconds = 0",
                "similarity_enabled = true",
            ]
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)

    assert len(config["warnings"]) >= 3
    assert "similarity_threshold" not in config["structural_scan"]


def test_scanner_timeout_records_failed_status_without_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.code_quality_similarity import semantic_similarity_scan

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/similarity-ts" if name == "similarity-ts" else None

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["similarity-ts"], timeout=1)

    monkeypatch.setattr("quality_runner.code_quality_similarity.shutil.which", fake_which)
    monkeypatch.setattr("quality_runner.code_quality_similarity.subprocess.run", fake_run)

    result = semantic_similarity_scan(tmp_path, policy=_policy(), disabled_groups=set())

    assert result["clusters"] == []
    assert result["scanner_status"][0]["status"] == "failed"


def test_regex_duplicate_detector_still_works_without_external_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    body = "\n".join(
        [
            "export function repeated(value: string) {",
            "  const local = value.trim();",
            "  return local.toUpperCase();",
            "}",
            "export function repeatedAgain(other: string) {",
            "  const local = other.trim();",
            "  return local.toUpperCase();",
            "}",
        ]
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text(body + "\n", encoding="utf-8")
    monkeypatch.setattr("quality_runner.code_quality_similarity.shutil.which", lambda _: None)

    result = create_code_quality_scan(tmp_path, scan={"run_id": "scan-001"}, config={})

    dup_clusters = [cluster for cluster in result["duplicate_clusters"] if cluster["id"].startswith("DUP-")]
    assert dup_clusters
    assert any(finding["rule_id"] == "near-duplicate-function" for finding in result["findings"])


def test_similarity_fingerprint_stable_when_line_numbers_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner.code_quality_similarity import semantic_similarity_scan

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.ts").write_text("export function parseFoo() {}\n", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/similarity-ts" if name == "similarity-ts" else None

    outputs = [
        PAIR_OUTPUT,
        PAIR_OUTPUT.replace("10-21", "12-23").replace("40-51", "42-53"),
    ]
    state = {"index": 0}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        output = outputs[state["index"]]
        state["index"] += 1
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr("quality_runner.code_quality_similarity.shutil.which", fake_which)
    monkeypatch.setattr("quality_runner.code_quality_similarity.subprocess.run", fake_run)

    first = semantic_similarity_scan(tmp_path, policy=_policy(), disabled_groups=set())
    second = semantic_similarity_scan(tmp_path, policy=_policy(), disabled_groups=set())

    assert first["findings"][0]["fingerprint"] == second["findings"][0]["fingerprint"]


def test_python_output_style_parses_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quality_runner.code_quality_similarity import semantic_similarity_scan

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def parse_foo():\n    pass\n", encoding="utf-8")

    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/similarity-py" if name == "similarity-py" else None

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, PYTHON_OUTPUT, "")

    monkeypatch.setattr("quality_runner.code_quality_similarity.shutil.which", fake_which)
    monkeypatch.setattr("quality_runner.code_quality_similarity.subprocess.run", fake_run)

    result = semantic_similarity_scan(tmp_path, policy=_policy(), disabled_groups=set())

    assert len(result["clusters"]) == 1
    assert result["findings"][0]["rule_id"] == "semantic-similarity-pair"


def test_similarity_disabled_skips_scanners(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quality_runner.code_quality_similarity import semantic_similarity_scan

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const value = 1;\n", encoding="utf-8")
    run = MagicMock()
    monkeypatch.setattr("quality_runner.code_quality_similarity.subprocess.run", run)

    result = semantic_similarity_scan(
        tmp_path,
        policy=_policy(similarity_enabled=False),
        disabled_groups=set(),
    )

    run.assert_not_called()
    assert result["scanner_status"][0]["status"] == "skipped"
