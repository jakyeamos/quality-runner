from __future__ import annotations

import ast
from pathlib import Path

import pytest

from quality_runner.core.review_packets import validate_prepared_packet

ROOT = Path(__file__).parents[1]


def test_legacy_workflow_modules_are_application_facades() -> None:
    from quality_runner import workflow, workflow_verify
    from quality_runner.application import audit_workflows, verification_workflows

    assert workflow.inspect_payload is audit_workflows.inspect_payload
    assert workflow.run_payload is audit_workflows.run_payload
    assert workflow.verify_gates_payload is verification_workflows.verify_gates_payload
    assert workflow_verify.verify_gates_payload is verification_workflows.verify_gates_payload


def test_public_workflow_positional_slots_and_review_finding_facade_are_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from quality_runner import workflow
    from quality_runner.compatibility import legacy_workflow
    from quality_runner.core.review_contracts import ReviewFinding as CoreReviewFinding
    from quality_runner.review_report import ReviewFinding

    root_calls: dict[str, object] = {}
    legacy_calls: dict[str, object] = {}

    def root_refresh(**kwargs: object) -> dict[str, object]:
        root_calls.update(kwargs)
        return {"schema": "test-refresh"}

    def legacy_refresh(**kwargs: object) -> dict[str, object]:
        legacy_calls.update(kwargs)
        return {"schema": "test-refresh"}

    monkeypatch.setattr(workflow, "_refresh_payload", root_refresh)
    legacy_args = (
        tmp_path,
        "legacy-refresh",
        None,
        None,
        None,
        120,
        None,
        None,
        None,
        None,
        None,
        False,
        True,
    )

    assert workflow.refresh_payload(*legacy_args) == {"schema": "test-refresh"}
    assert root_calls["allow_mutating_gates"] is True
    assert root_calls["execute_discovered_gates"] is False

    assert legacy_workflow.refresh_payload(*legacy_args, refresh_runner=legacy_refresh) == {
        "schema": "test-refresh"
    }
    assert legacy_calls["allow_mutating_gates"] is True
    assert legacy_calls["execute_discovered_gates"] is False
    assert ReviewFinding is CoreReviewFinding


def test_application_workflows_do_not_depend_on_legacy_workflow_paths() -> None:
    legacy_modules = {"quality_runner.workflow", "quality_runner.workflow_verify"}
    application_modules = (
        "audit_workflows.py",
        "journey_outcomes.py",
        "review_context_factory.py",
        "review_reporting.py",
        "verification_workflows.py",
    )

    for module_name in application_modules:
        imports = _imports(ROOT / "quality_runner" / "application" / module_name)
        assert not any(
            import_name in legacy_modules
            or import_name.startswith("quality_runner.compatibility.")
            or import_name.startswith("quality_runner.cli")
            for import_name in imports
        )


def test_review_context_compatibility_wrappers_preserve_both_combined_shapes(
    tmp_path: Path,
) -> None:
    from quality_runner import review_context, review_report
    from quality_runner.application import review_context_factory, review_reporting

    legacy_options = review_context.normalize_review_options(
        mode="combined",
        scope="project",
        breadth="related",
        task="Preserve the direct combined projection",
        include_known_issues=True,
        known_issues=["known-001"],
        previous_summary="Prior implementation notes",
    )
    strict_options = review_context_factory.normalize_review_options(
        mode="combined",
        scope="project",
        breadth="related",
        task="Preserve the direct combined projection",
        include_known_issues=True,
        known_issues=["known-001"],
        previous_summary="Prior implementation notes",
    )
    assert legacy_options == strict_options

    legacy_direct = review_context.build_review_packet(
        repo_root=tmp_path,
        run_id="legacy-direct",
        options=legacy_options,
        repository_state={"branch": "main"},
        changed_files=["src/app.py"],
    )
    application_direct = review_context_factory.build_review_packet(
        repo_root=tmp_path,
        run_id="legacy-direct",
        options=strict_options,
        repository_state={"branch": "main"},
        changed_files=["src/app.py"],
    )
    assert legacy_direct == application_direct
    assert legacy_direct["mode"] == "combined"
    assert "packets" not in legacy_direct
    assert legacy_direct["task"] == "Preserve the direct combined projection"

    legacy_prepared = review_context.build_review_context(
        repo_root=tmp_path,
        run_id="prepared-combined",
        options=legacy_options,
    )
    application_prepared = review_context_factory.build_review_context(
        repo_root=tmp_path,
        run_id="prepared-combined",
        options=strict_options,
    )
    assert legacy_prepared == application_prepared
    assert [packet["mode"] for packet in legacy_prepared["packets"]] == ["task", "blind"]
    assert "task" not in legacy_prepared
    validate_prepared_packet(application_prepared)
    assert review_report.build_review_report is review_reporting.build_review_report


def test_review_application_modules_do_not_depend_on_context_or_report_facades() -> None:
    forbidden_modules = {
        "quality_runner.review_context",
        "quality_runner.review_report",
        "quality_runner.review_types",
    }
    application_modules = (
        "fresh_review.py",
        "review_context_factory.py",
        "review_reporting.py",
        "review_responses.py",
    )

    for module_name in application_modules:
        imports = _imports(ROOT / "quality_runner" / "application" / module_name)
        assert not imports.intersection(forbidden_modules)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
