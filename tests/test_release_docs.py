from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_docs_describe_current_release_plan_and_release_history() -> None:
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

    assert "## 0.2.1 - 2026-07-02" in changelog
    assert "repo-owned quality gates" in changelog
    assert "Ponytail-debt rules" in changelog

    assert "## 0.3.0 - 2026-07-04" in changelog
    assert "release-smoke" in changelog
    assert "total refresh timeouts" in changelog

    assert "## 0.3.1 - 2026-07-04" in changelog
    assert "compatibility imports, console scripts, MCP tools" in changelog
    assert "v0.3.1" in release_docs
    assert "Do not reuse `v0.1.0`, `v0.2.0`, or `v0.3.0`" in release_docs
    assert "Do not reuse `v0.1.0`" in release_docs
    assert "Trusted Publisher" in release_docs
    assert "before tagging" in release_docs
    assert "quality-runner release-smoke --json" in release_docs
    assert "repo-quality-certifier plan" in release_docs
    assert "repo-quality-certifier-mcp" in release_docs
    assert (
        "quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --handoff-output handoff.md --json"
        in cli_docs
    )


def test_plugin_manifest_versions_match_project_version() -> None:
    import json

    from quality_runner import __version__

    manifest = json.loads(
        (ROOT / "quality_runner" / "plugin" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["version"] == __version__


def test_release_docs_include_example_handoffs() -> None:
    examples_root = ROOT / "docs" / "examples"
    examples = {
        "handoff-clean.md": "Status: gates-clean",
        "handoff-blocked.md": "Status: gates-blocked",
        "handoff-timeout.md": "workflow-timeout",
    }

    for name, expected in examples.items():
        content = (examples_root / name).read_text(encoding="utf-8")
        assert "# Quality Runner Agent Handoff" in content
        assert expected in content
