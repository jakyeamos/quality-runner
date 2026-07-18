from __future__ import annotations

import ast
import json
from pathlib import Path

from quality_runner.application.read_only_audit import (
    analyze_read_only_audit,
    plan_read_only_audit,
)
from quality_runner.core.audit_contracts import AuditRequest
from quality_runner.scan_scope import is_security_surface_file
from test_support.quality_runner_fixtures import write_js_fixture


def test_read_only_analysis_shares_one_scope_between_security_and_code_quality(
    tmp_path: Path,
) -> None:
    write_js_fixture(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "unsafe.js").write_text("eval(input)\n", encoding="utf-8")
    excluded_route = tmp_path / "vendor" / "app" / "api" / "internal"
    excluded_route.mkdir(parents=True)
    (excluded_route / "route.ts").write_text("eval(input)\n", encoding="utf-8")

    analysis = analyze_read_only_audit(_request(tmp_path, "shared-scope"))

    scope_paths = [item.path for item in analysis.text_scan_scope.files]
    code_quality_paths = [
        item["path"]
        for item in analysis.code_quality_scan["accountability"]
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    ]
    security_paths = {
        item["file"]
        for item in analysis.security_scan["candidates"]
        if isinstance(item, dict) and isinstance(item.get("file"), str)
    }

    assert code_quality_paths == scope_paths
    assert security_paths == {"src/unsafe.js"}
    assert analysis.security_scan["surfaces"]["api_routes"] is False
    assert all(not path.startswith("vendor/") for path in scope_paths)


def test_read_only_planning_validates_before_the_artifact_renderer_runs(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    analysis = analyze_read_only_audit(_request(tmp_path, "read-only-plan"))
    planned = plan_read_only_audit(analysis, artifact_paths={})

    assert planned.status == "planned"
    assert planned.audit_report["schema"] == "quality-runner-audit-report-v0.1"
    assert planned.remediation_plan["schema"] == "quality-runner-remediation-plan-v0.1"
    assert planned.remediation_context is not None
    assert planned.remediation_context["schema"] == "quality-runner-remediation-context-v0.1"
    assert planned.remediation_plan["remediation_context"]["status"] == "needs-understanding"
    assert planned.handoff["remediation_context"]["blocking"] is True
    assert all(
        isinstance(slice_item.get("context_id"), str)
        for slice_item in planned.remediation_plan["slices"]
    )
    assert analysis.code_quality_scan["analysis_cache"]["status"] == "disabled"
    assert analysis.security_scan["analysis_cache"]["status"] == "disabled"
    assert not (tmp_path / ".quality-runner").exists()


def test_shared_scope_includes_go_module_metadata_for_security_surface_detection(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text("module example.com/fixture\n", encoding="utf-8")

    analysis = analyze_read_only_audit(_request(tmp_path, "go-module-scope"))

    assert "go.mod" not in {item.path for item in analysis.text_scan_scope.files}
    assert "go.mod" in analysis.text_scan_scope.security_surface_paths
    assert analysis.security_scan["surfaces"]["dependency_manifest"] is True


def test_shared_scope_retains_go_api_review_gates_without_changing_code_quality_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "go.mod").write_text("module example.com/fixture\n", encoding="utf-8")
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    (api_dir / "handler.go").write_text("package api\n", encoding="utf-8")

    analysis = analyze_read_only_audit(_request(tmp_path, "go-api-scope"))

    gates = {
        item["id"]
        for item in analysis.security_scan["agent_review_gates"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    assert "api/handler.go" in analysis.text_scan_scope.security_surface_paths
    assert "api/handler.go" not in {item.path for item in analysis.text_scan_scope.files}
    assert analysis.security_scan["surfaces"]["api_routes"] is True
    assert {"security_api_route_auth_review", "security_auth_surface_review"} <= gates


def test_shared_scope_retains_unknown_extension_api_review_gates(tmp_path: Path) -> None:
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    (api_dir / "Handler.kt").write_text("package api\n", encoding="utf-8")

    analysis = analyze_read_only_audit(_request(tmp_path, "kotlin-api-scope"))

    gates = {
        item["id"]
        for item in analysis.security_scan["agent_review_gates"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    assert "api/Handler.kt" in analysis.text_scan_scope.security_surface_paths
    assert analysis.security_scan["surfaces"]["api_routes"] is True
    assert {"security_api_route_auth_review", "security_auth_surface_review"} <= gates


def test_security_surface_scope_is_independent_of_the_code_quality_text_budget(
    tmp_path: Path,
) -> None:
    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner.structural_scan]\nmax_text_files = 1\n",
        encoding="utf-8",
    )
    (tmp_path / "a.ts").write_text("export const value = 1;\n", encoding="utf-8")
    api_dir = tmp_path / "api"
    api_dir.mkdir()
    (api_dir / "route.ts").write_text("export const route = {};\n", encoding="utf-8")

    analysis = analyze_read_only_audit(_request(tmp_path, "surface-budget"))

    gates = {
        item["id"]
        for item in analysis.security_scan["agent_review_gates"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    assert analysis.code_quality_scan["summary"]["scan_budget"]["max_text_files"] == 1
    assert "api/route.ts" in analysis.text_scan_scope.security_surface_paths
    assert analysis.security_scan["surfaces"]["api_routes"] is True
    assert {"security_api_route_auth_review", "security_auth_surface_review"} <= gates


def test_security_surface_budget_is_reserved_for_actual_surface_paths() -> None:
    assert is_security_surface_file(Path("a.ts"), "a.ts") is False
    assert is_security_surface_file(Path("z/api/route.ts"), "z/api/route.ts") is True
    assert is_security_surface_file(Path("handler.kt"), "handlers/webhook/Handler.kt") is True
    assert is_security_surface_file(Path("go.mod"), "go.mod") is True


def test_shared_scope_retains_src_routes_api_review_gates(tmp_path: Path) -> None:
    route_dir = tmp_path / "src" / "routes"
    route_dir.mkdir(parents=True)
    (route_dir / "users.ts").write_text("export const users = {};\n", encoding="utf-8")

    analysis = analyze_read_only_audit(_request(tmp_path, "src-routes-scope"))

    gates = {
        item["id"]
        for item in analysis.security_scan["agent_review_gates"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    assert "src/routes/users.ts" in analysis.text_scan_scope.security_surface_paths
    assert analysis.security_scan["surfaces"]["api_routes"] is True
    assert {"security_api_route_auth_review", "security_auth_surface_review"} <= gates


def test_include_overrides_do_not_change_discovery_or_standards_inputs(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "model.ts").write_text("export const model = {};\n", encoding="utf-8")

    analysis = analyze_read_only_audit(
        _request(tmp_path, "scoped-override", include_ignored_paths=("data",))
    )

    assert "data/model.ts" in {
        item["path"]
        for item in analysis.code_quality_scan["accountability"]
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    standards_config = analysis.standards_packet["config"]
    assert isinstance(standards_config, dict)
    assert "include_ignored_paths" not in standards_config.get("structural_scan", {})


def test_run_renderer_preserves_v1_artifact_path_snapshots(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    write_js_fixture(tmp_path)

    payload = run_payload(
        repo_root=tmp_path,
        run_id="artifact-path-snapshots",
        profile="default",
        intent={"goal": "Preserve artifact compatibility"},
    )
    artifact_paths = payload["artifact_paths"]
    manifest = json.loads(Path(artifact_paths["run_manifest_json"]).read_text(encoding="utf-8"))
    handoff = json.loads(Path(artifact_paths["agent_handoff_json"]).read_text(encoding="utf-8"))

    assert "intent_json" not in handoff["artifact_paths"]
    assert "slice_specs_dir" not in handoff["artifact_paths"]
    assert "intent_json" in manifest["artifact_paths"]
    assert "slice_specs_dir" not in manifest["artifact_paths"]
    assert {"intent_json", "slice_specs_dir"} <= set(artifact_paths)


def test_audit_contracts_do_not_depend_on_workflow_layers() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "quality_runner" / "core" / "audit_contracts.py").read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "Any" not in source
    assert not any(module.startswith("quality_runner") for module in imported_modules)


def _request(
    repo_root: Path,
    run_id: str,
    *,
    include_ignored_paths: tuple[str, ...] = (),
) -> AuditRequest:
    return AuditRequest(
        repo_root=repo_root,
        run_id=run_id,
        profile="default",
        ci_status_json=None,
        include_ignored_paths=include_ignored_paths,
        branch_warnings=(),
        skill_review_report=None,
        intent=None,
    )
