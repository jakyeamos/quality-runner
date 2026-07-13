from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_legacy_workflow_modules_are_application_facades() -> None:
    from quality_runner import workflow, workflow_verify
    from quality_runner.application import audit_workflows, verification_workflows

    assert workflow.inspect_payload is audit_workflows.inspect_payload
    assert workflow.run_payload is audit_workflows.run_payload
    assert workflow.verify_gates_payload is verification_workflows.verify_gates_payload
    assert workflow_verify.verify_gates_payload is verification_workflows.verify_gates_payload


def test_application_workflows_do_not_depend_on_legacy_workflow_paths() -> None:
    legacy_modules = {"quality_runner.workflow", "quality_runner.workflow_verify"}
    application_modules = (
        "audit_workflows.py",
        "journey_outcomes.py",
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


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
