from __future__ import annotations

from pathlib import Path
from typing import Any


def _finding(finding_id: str, *, category: str = "capability") -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": "warning",
        "category": category,
        "summary": f"{finding_id} summary",
        "recommended_fix": f"Fix {finding_id}",
        "verification": ["pnpm test"],
        "score": 12,
    }


def test_remediation_slices_gain_handoff_metadata(tmp_path: Path) -> None:
    from quality_runner.manifest import git_state_for_repo
    from quality_runner.planning import build_remediation_plan

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "app.ts").write_text("function parse(input: any) {\n  return input\n}\n")
    (repo / "PRODUCT.md").write_text("# Product\n", encoding="utf-8")

    plan = build_remediation_plan(
        audit_report={
            "run_id": "handoff-run",
            "profile": "default",
            "findings": [_finding("missing-typecheck")],
        },
        capability_map={"missing": [], "warnings": []},
        repo_root=repo,
        git_state=git_state_for_repo(repo),
    )
    assert plan["slices"]
    first = plan["slices"][0]
    assert first["stop_conditions"]
    assert first["scope"]["in_scope"]
    assert first["scope"]["out_of_scope"]
    assert first["leverage"]["rank"] >= 0


def test_slice_spec_markdown_includes_required_sections() -> None:
    from quality_runner.handoff_lint import validate_slice_spec_content
    from quality_runner.slice_specs import render_slice_spec_markdown

    slice_item = {
        "id": "remediate-missing-typecheck",
        "title": "Remediate missing-typecheck",
        "priority": "high",
        "impact": "Missing typecheck blocks safe refactors.",
        "findings": [{"id": "missing-typecheck", "summary": "typecheck missing"}],
        "verification_gates": ["pnpm typecheck"],
        "actions": ["Add typecheck script."],
        "scope": {"in_scope": ["package.json scripts"], "out_of_scope": ["Unrelated files"]},
        "stop_conditions": ["Stop if typecheck already exists."],
        "planned_at": {"head": "abc123", "branch": "main", "dirty": False},
        "drift_check": {
            "command": "git diff --stat abc123..HEAD -- package.json",
            "paths": ["package.json"],
        },
    }
    content = render_slice_spec_markdown(
        slice_item,
        run_id="handoff-run",
        intent_docs=[{"type": "product", "path": "PRODUCT.md"}],
    )
    result = validate_slice_spec_content(content)
    assert result["passed"] is True
    assert "## STOP conditions" in content
    assert "PRODUCT.md" in content


def test_discover_intent_docs_finds_product_and_adrs(tmp_path: Path) -> None:
    from quality_runner.intent_docs import discover_intent_docs

    repo = tmp_path / "repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "PRODUCT.md").write_text("# Product\n", encoding="utf-8")
    (repo / "docs" / "adr" / "0001-sync.md").write_text("# ADR\n", encoding="utf-8")

    docs = discover_intent_docs(repo)
    types = {doc["type"] for doc in docs}
    assert "product" in types
    assert "adr" in types


def test_validate_handoff_quality_requires_slice_guards() -> None:
    from quality_runner.handoff_lint import validate_handoff_quality

    handoff = {
        "schema": "quality-runner-agent-handoff-v0.2",
        "status": "planned",
        "implementation_allowed": False,
        "artifact_paths": {},
        "warnings": [],
        "finding_ids": ["missing-typecheck"],
        "slice_ids": ["remediate-missing-typecheck"],
        "verification_gates": ["pnpm test"],
        "next_slice": {
            "id": "remediate-missing-typecheck",
            "title": "Remediate",
            "priority": "high",
            "findings": [
                {
                    "id": "missing-typecheck",
                    "severity": "warning",
                    "category": "capability",
                    "summary": "x",
                }
            ],
            "actions": ["fix"],
            "verification_gates": ["pnpm test"],
        },
    }
    plan = {
        "slices": [
            {
                "id": "remediate-missing-typecheck",
                "title": "Remediate",
                "priority": "high",
                "findings": [
                    {
                        "id": "missing-typecheck",
                        "severity": "warning",
                        "category": "capability",
                        "summary": "x",
                    }
                ],
                "actions": ["fix"],
                "verification_gates": ["pnpm test"],
            }
        ]
    }
    result = validate_handoff_quality(handoff, remediation_plan=plan)
    assert result["passed"] is False
    assert any("STOP conditions" in error for error in result["errors"])


def test_example_slice_spec_passes_lint() -> None:
    from pathlib import Path

    from quality_runner.handoff_lint import validate_slice_spec_content

    example = Path(__file__).resolve().parents[1] / "docs/examples/slice-spec-structural-harden.md"
    result = validate_slice_spec_content(example.read_text(encoding="utf-8"))
    assert result["passed"] is True, result["errors"]
