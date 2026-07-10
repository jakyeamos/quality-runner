from __future__ import annotations

import json
from pathlib import Path

import pytest


def _report() -> dict[str, object]:
    from quality_runner.review_report import build_review_report
    from tests.test_review_report import _finding

    return build_review_report(
        run_id="review-artifacts",
        mode="task",
        scope="task",
        breadth="focused",
        findings=[_finding()],
        evidence_used=["src/routes.py"],
        evidence_unavailable=["browser access"],
        exclusions=["styling"],
        adapter_status="review-complete",
        task_provenance="task.md",
    )


def _context() -> dict[str, object]:
    return {
        "schema": "quality-runner-review-context-v0.1",
        "run_id": "review-artifacts",
        "mode": "task",
        "scope": "task",
        "breadth": "focused",
        "task": "Wire the settings route",
        "freshness": {
            "new_invocation_required": True,
            "prior_review_context_included": False,
            "previous_agent_summary_included": False,
            "hidden_reasoning_included": False,
            "active_cycle": False,
        },
    }


def test_persist_review_artifacts_writes_canonical_json_and_markdown(tmp_path: Path) -> None:
    from quality_runner.review_artifacts import persist_review_artifacts

    paths = persist_review_artifacts(
        repo_root=tmp_path,
        run_id="review-artifacts",
        manifest={"schema": "quality-runner-review-manifest-v0.1"},
        context=_context(),
        report=_report(),
    )
    run_dir = tmp_path / ".quality-runner" / "runs" / "review-artifacts"

    assert set(paths) == {
        "review_manifest_json",
        "review_context_json",
        "review_report_json",
        "review_report_md",
        "review_agent_packet_md",
        "review_fix_prompts_md",
    }
    assert json.loads((run_dir / "review-report.json").read_text()) ["severity_counts"]["high"] == 1
    markdown = (run_dir / "review-report.md").read_text()
    assert "Review complete: 0 critical, 1 high, 0 medium issues found." in markdown
    assert "## Suspected issues" in markdown
    assert "## Remaining uncertainty" in markdown


def test_fix_prompts_preserve_scope_and_read_only_boundary(tmp_path: Path) -> None:
    from quality_runner.review_artifacts import persist_review_artifacts

    persist_review_artifacts(
        repo_root=tmp_path,
        run_id="review-prompts",
        manifest={},
        context=_context(),
        report={**_report(), "run_id": "review-prompts"},
    )
    prompts = (tmp_path / ".quality-runner/runs/review-prompts/review-fix-prompts.md").read_text()

    assert "investigate" in prompts.lower()
    assert "does not edit source files" in prompts.lower()
    assert "FR-001" in prompts
    assert "src/routes.py" in prompts


def test_no_save_does_not_create_shareable_artifacts(tmp_path: Path) -> None:
    from quality_runner.review_artifacts import persist_review_artifacts

    paths = persist_review_artifacts(
        repo_root=tmp_path,
        run_id="review-no-save",
        manifest={},
        context=_context(),
        report=_report(),
        save=False,
    )

    assert paths == {}
    assert not (tmp_path / ".quality-runner").exists()


def test_unsafe_run_id_and_symlinked_run_directory_are_rejected(tmp_path: Path) -> None:
    from quality_runner.review_artifacts import persist_review_artifacts

    with pytest.raises(ValueError, match="single path segment"):
        persist_review_artifacts(
            repo_root=tmp_path,
            run_id="../escape",
            manifest={},
            context=_context(),
            report=_report(),
        )

    root = tmp_path / ".quality-runner"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (root / "runs").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        persist_review_artifacts(
            repo_root=tmp_path,
            run_id="review-symlink",
            manifest={},
            context=_context(),
            report=_report(),
        )
