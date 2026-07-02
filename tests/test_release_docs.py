from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_docs_describe_0_2_0_structural_quality_artifacts() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    cli_docs = (ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
    release_docs = (ROOT / "docs" / "release.md").read_text(encoding="utf-8")

    assert "## 0.2.0 - 2026-07-02" in changelog
    for term in (
        "structural/code-quality scan",
        "resolution ledger",
        "grouped remediation",
        "accepted dispositions",
        "scanner module split",
    ):
        assert term in changelog

    assert "code-quality-scan.json" in cli_docs
    assert "resolution-ledger.json" in cli_docs
    assert "resolution-ledger.md" in cli_docs

    assert "v0.2.0" in release_docs
    assert "Do not reuse `v0.1.0`" in release_docs
    assert "Trusted Publisher" in release_docs
    assert "before tagging" in release_docs
