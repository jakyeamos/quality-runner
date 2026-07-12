from __future__ import annotations

import json
import re
import tomllib
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
    assert "quality-runner review" in cli_docs
    assert "review-agent-packet.md" in cli_docs

    assert "## 0.2.1 - 2026-07-02" in changelog
    assert "repo-owned quality gates" in changelog
    assert "Ponytail-debt rules" in changelog

    assert "## 0.3.0 - 2026-07-04" in changelog
    assert "release-smoke" in changelog
    assert "total refresh timeouts" in changelog

    assert "## 0.3.1 - 2026-07-04" in changelog
    assert "compatibility imports, console scripts, MCP tools" in changelog
    assert "## 0.4.0 - 2026-07-07" in changelog
    assert "multi-repo `rollout` workflow" in changelog
    assert "gate controller runs" in changelog
    assert "security scan surfaces" in changelog
    assert "v0.5.1" in release_docs
    assert (
        "Do not reuse `v0.1.0`, `v0.2.0`, `v0.2.1`, `v0.3.0`, `v0.3.1`, `v0.4.0`, or"
        in release_docs
    )
    assert "Do not reuse `v0.1.0`" in release_docs
    assert "Trusted Publisher" in release_docs
    assert "before tagging" in release_docs
    assert "quality-runner release-smoke --json" in release_docs
    assert "repo-quality-certifier plan" in release_docs
    assert "repo-quality-certifier-mcp" in release_docs
    assert (
        "tag, built wheel, installed CLI/MCP commands, plugin manifest, and citation"
        in release_docs
    )
    assert "--execute-gates --worktree-mode disposable" in release_docs
    assert (
        "quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --handoff-output handoff.md --json"
        in cli_docs
    )


def test_plugin_manifest_and_citation_metadata_follow_their_release_contracts() -> None:
    from quality_runner import __version__

    manifest = json.loads(
        (ROOT / "quality_runner" / "plugin" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["version"] == __version__
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    citation_version = re.search(r'^version: "(?P<version>[^\"]+)"$', citation, re.MULTILINE)
    citation_date = re.search(
        r'^date-released: "(?P<date>\d{4}-\d{2}-\d{2})"$', citation, re.MULTILINE
    )
    assert citation_version is not None
    assert citation_date is not None
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {citation_version.group('version')} - {citation_date.group('date')}" in changelog

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in pyproject["project"]
    assert pyproject["project"]["dynamic"] == ["version"]
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "quality_runner._version.__version__"
    }

    from quality_runner.mcp import list_tools

    assert set(manifest["mcp"]["tools"]) == {tool["name"] for tool in list_tools()}


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
