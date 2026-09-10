"""Environment findings preserve flag identity through task comparison."""

from pathlib import Path
from typing import Any

import pytest

from quality_runner.code_quality import create_code_quality_scan
from quality_runner.task_findings import normalize_findings

SOURCE = "const base = process.env.GITHUB_BASE_SHA || process.env.BASE_SHA;\n"


def _scan(root: Path) -> dict[str, Any]:
    return create_code_quality_scan(root, scan={"run_id": "env-identity"}, config={})


def _flags(scan: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in scan["findings"] if row["rule_id"] == "undocumented-env-flag"]


def test_same_line_flags_have_distinct_stable_task_identities(tmp_path: Path) -> None:
    source = tmp_path / "check.ts"
    source.write_text(SOURCE)
    first = _scan(tmp_path)
    rows = _flags(first)
    assert len(rows) == 2
    assert len({row["fingerprint"] for row in rows}) == 2
    normalized = normalize_findings(
        code_quality_scan=first,
        security_scan={"coverage": "complete", "candidates": []},
        prevention={},
    )
    assert normalized["ambiguities"] == []
    source.write_text("// moved down\n" + SOURCE)
    assert [row["fingerprint"] for row in _flags(_scan(tmp_path))] == [
        row["fingerprint"] for row in rows
    ]


@pytest.mark.parametrize(
    ("documentation", "expected"),
    [
        ("GITHUB_BASE_SHA is the pull request base.", ["BASE_SHA"]),
        ("BASE_SHA is a local fallback.", ["GITHUB_BASE_SHA"]),
        ("`GITHUB_BASE_SHA` and `BASE_SHA` select revisions.", []),
        ("PREFIX_GITHUB_BASE_SHA_SUFFIX is another setting.", ["BASE_SHA", "GITHUB_BASE_SHA"]),
    ],
)
def test_documentation_matches_the_complete_flag_name(
    tmp_path: Path, documentation: str, expected: list[str]
) -> None:
    (tmp_path / "check.ts").write_text(SOURCE)
    (tmp_path / "README.md").write_text(documentation)
    rows = _flags(_scan(tmp_path))
    assert sorted(row["expected_improvement"].split()[1] for row in rows) == expected
