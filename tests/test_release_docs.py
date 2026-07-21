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
    upgrade_docs = (ROOT / "docs" / "upgrade.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

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
    assert "unreleased candidate" in release_docs
    assert "PyPI verification succeeds" in release_docs
    assert "built wheel" in release_docs
    assert "Trusted Publisher" in release_docs
    assert "before tagging" in release_docs
    assert "uv sync --locked --all-groups" in release_docs
    assert "uv run --locked pip-audit" in release_docs
    assert "quality-runner release-smoke --json" in release_docs
    assert "quality-runner-mcp" in release_docs
    assert "uv tool install 'quality-runner==0.6.0' --force" in release_docs
    assert "--execute-gates --worktree-mode disposable" in release_docs
    assert "Upgrade and Compatibility Guide" in release_docs
    assert "review --legacy-output" in cli_docs
    assert "review --outcome" not in cli_docs
    assert "0.7.x" in upgrade_docs
    assert "0.8.0" in upgrade_docs
    assert "No artifact conversion is required" in upgrade_docs
    assert "quality_runner_review" in upgrade_docs
    assert "historical runtime-display mismatch" in upgrade_docs
    assert "uv tool list" in upgrade_docs
    assert "qr review /path/to/repo --mode blind --json" in readme
    assert "older `0.2.0` template" in release_docs
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
    assert manifest["commands"]["review"]["args"] == ["review"]
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
    skill = (ROOT / "quality_runner" / "plugin" / "SKILL.md").read_text(encoding="utf-8")
    assert ".quality-runner/runs/qr-<date-or-task>/agent-handoff.md" in skill
    assert ".quality-runner/exports/qr-handoff.md" not in skill


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


def test_agent_instructions_route_current_qr_surfaces() -> None:
    agent_usage = (ROOT / "docs" / "agent-usage.md").read_text(encoding="utf-8")
    plugin_skill = (ROOT / "quality_runner" / "plugin" / "SKILL.md").read_text(encoding="utf-8")

    for content in (agent_usage, plugin_skill):
        for term in (
            "qr doctor",
            "qr audit",
            "qr review",
            "qr verify",
            "qr runs",
            "quality-runner-outcome-v0.2",
            "--include-path",
            "--include-ignored-path",
            "scan_inclusions",
            "gate-respond",
            "review-delta",
            "release-smoke",
        ):
            assert term in content

    assert "plan contract prepare" in agent_usage
    assert "controller-report lint --strict" in agent_usage


def test_ci_and_release_workflows_smoke_built_wheel_outcome_and_mcp_surfaces() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    for workflow in (ci, release):
        assert "uv sync --locked --all-groups" in workflow
        assert "uv run --locked pip-audit" in workflow
        assert "quality-runner release-smoke --json" in workflow
        assert "quality-runner review" in workflow
        assert "review-default" in workflow
        assert "quality-runner-outcome-v0.2" in workflow
        assert "--legacy-output" in workflow
        assert '"method":"tools/list"' in workflow
        assert '"method":"tools/call"' in workflow
        assert "quality_runner_audit_outcome" in workflow
        assert "quality_runner_review_outcome" in workflow

    assert "fetch-depth: 0" in release
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" origin/main' in release


def test_security_and_research_docs_match_current_artifact_handling() -> None:
    artifacts = (ROOT / "docs" / "artifacts.md").read_text(encoding="utf-8")
    threat_model = (ROOT / "docs" / "threat-model.md").read_text(encoding="utf-8")
    troubleshooting = (ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    research = (ROOT / "RESEARCH_READY.md").read_text(encoding="utf-8")

    assert "Handling generated artifacts" in artifacts
    assert "quoted source literals are redacted before fingerprinting" in artifacts
    assert "artifact secret-free" in artifacts
    assert "Artifact Contract" in threat_model
    assert "A generated artifact might contain sensitive data" in troubleshooting
    assert "redaction bypass" in security
    assert "uv sync --locked --all-groups" in research
    assert "Full type/format readiness is not yet clean" not in research
