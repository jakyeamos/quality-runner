from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repo_quality_certifier import (  # noqa: E402
    build_tmcp_expert_enrichment,
    validate_tmcp_expert_enrichment,
)
from repo_quality_certifier.mcp import call_tool, handle_jsonrpc_message, list_tools  # noqa: E402


def _write_certifier_fixture(repo: Path) -> None:
    (repo / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "format": "prettier --check .",
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                    "test": "vitest run",
                    "build": "vite build",
                    "dead-code": "knip",
                    "secret-scan": "detect-secrets scan",
                    "dependency-security": "pnpm audit",
                    "runtime:smoke": "playwright test --grep @runtime-smoke",
                    "pre-pr": "pnpm pre-pr-readiness",
                    "release:check": "pnpm deploy:preview:watch",
                    "healthcheck": "python scripts/healthcheck.py",
                }
            }
        ),
        encoding="utf-8",
    )
    (repo / "tsconfig.json").write_text("{}", encoding="utf-8")
    (repo / ".pre-cr.json").write_text("{}", encoding="utf-8")
    (repo / ".git" / "info").mkdir(parents=True)


def test_standalone_import_does_not_load_aios_tmcp_runtime() -> None:
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(ROOT)!r}); "
        "import repo_quality_certifier; "
        "print('services.tmcp_runtime' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_standalone_tmcp_enrichment_has_valid_fallback(tmp_path: Path) -> None:
    scan = {
        "repo_path": str(tmp_path),
        "project_kind": "library_package",
    }
    gate_matrix = {
        "repo_path": str(tmp_path),
        "project_kind": "library_package",
        "gates": [],
    }

    enrichment = build_tmcp_expert_enrichment(
        scan=scan,
        gate_matrix=gate_matrix,
        run_id="standalone-run",
    )

    assert enrichment["status"] == "not_requested"
    assert enrichment["fallback"] == "aios_standard_rubric"
    assert validate_tmcp_expert_enrichment(enrichment)["passed"] is True


def test_standalone_tmcp_compiler_uses_product_domain(tmp_path: Path) -> None:
    calls: dict[str, object] = {}

    def fake_compiler(**kwargs: object) -> dict[str, object]:
        calls.update(kwargs)
        return {
            "schema": "fake-tmcp-packet",
            "status": "compiled",
            "selected_nodes": [],
        }

    enrichment = build_tmcp_expert_enrichment(
        scan={"repo_path": str(tmp_path), "project_kind": "library_package"},
        gate_matrix={"repo_path": str(tmp_path), "project_kind": "library_package", "gates": []},
        run_id="standalone-run",
        tmcp_compiler=fake_compiler,
    )

    assert calls["domain"] == "repo_quality_certifier"
    assert enrichment["status"] == "insufficient_source"


def test_module_cli_plan_writes_external_fixture_artifacts(tmp_path: Path) -> None:
    _write_certifier_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repo_quality_certifier",
            "plan",
            "--repo-root",
            str(tmp_path),
            "--run-id",
            "external-fixture",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "repo-quality-certifier-plan-result-v0.1"
    assert payload["certifier_role"] == "standalone_quality_certification_engine"
    assert payload["phase_scope_policy"] == "repo_local_gate_scoped"
    assert payload["repo_local_phases"]
    assert Path(payload["artifact_paths"]["gate_matrix_json"]).exists()
    enrichment = json.loads(
        Path(payload["artifact_paths"]["tmcp_expert_enrichment_json"]).read_text(encoding="utf-8")
    )
    assert enrichment["status"] == "not_requested"
    assert "services.tmcp_runtime" not in result.stderr


def test_module_cli_doc_quality_validates_external_fixture(tmp_path: Path) -> None:
    _write_certifier_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "repo_quality_certifier",
            "doc-quality",
            "--repo-root",
            str(tmp_path),
            "--run-id",
            "external-fixture-docs",
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["schema"] == "repo-quality-certifier-doc-quality-result-v0.1"
    assert payload["passed"] is True
    assert payload["ready_for_phase_planning"] is True
    assert payload["ready_for_execution"] is True
    assert Path(payload["artifact_paths"]["adoption_doc_quality_json"]).exists()


def test_certifier_rejects_unsafe_run_ids_and_symlinked_output_ancestors(tmp_path: Path) -> None:
    from repo_quality_certifier.cli import build_plan_payload

    _write_certifier_fixture(tmp_path)
    for run_id in ("../escape", "/tmp/escape", "nested\\escape"):
        try:
            build_plan_payload(repo_root=tmp_path, run_id=run_id)
        except ValueError as error:
            assert str(error) == "run_id must be a non-empty single path segment"
        else:
            raise AssertionError(f"certifier accepted unsafe run ID: {run_id}")

    external = tmp_path / "external"
    (external / "nested").mkdir(parents=True)
    output_link = tmp_path / "output-link"
    output_link.symlink_to(external, target_is_directory=True)
    try:
        build_plan_payload(
            repo_root=tmp_path,
            run_id="safe-run",
            output_dir=output_link / "nested",
        )
    except ValueError as error:
        assert str(error) == "artifact output directory must not contain symlink components"
    else:
        raise AssertionError("certifier followed a symlinked output ancestor")

    assert not (external / "nested" / "gate-matrix.json").exists()


def test_mcp_lists_and_calls_certifier_tools(tmp_path: Path) -> None:
    _write_certifier_fixture(tmp_path)

    tools = list_tools()
    assert {tool["name"] for tool in tools} == {
        "repo_quality_certifier_plan",
        "repo_quality_certifier_doc_quality",
    }

    result = call_tool(
        "repo_quality_certifier_plan",
        {"repo_root": str(tmp_path), "run_id": "mcp-fixture"},
    )

    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["schema"] == "repo-quality-certifier-plan-result-v0.1"
    assert Path(structured["artifact_paths"]["rollout_plan_json"]).exists()


def test_mcp_jsonrpc_tools_call(tmp_path: Path) -> None:
    _write_certifier_fixture(tmp_path)

    response = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "repo_quality_certifier_doc_quality",
                "arguments": {
                    "repo_root": str(tmp_path),
                    "run_id": "mcp-doc-quality-fixture",
                },
            },
        }
    )

    assert response is not None
    assert response["id"] == 1
    structured = response["result"]["structuredContent"]
    assert structured["schema"] == "repo-quality-certifier-doc-quality-result-v0.1"
    assert structured["passed"] is True


def test_plugin_manifest_points_to_cli_mcp_and_skill() -> None:
    manifest_path = ROOT / "repo_quality_certifier" / "plugin" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema"] == "repo-quality-certifier-plugin-manifest-v0.1"
    assert manifest["commands"]["plan"]["command"] == "repo-quality-certifier"
    assert manifest["commands"]["doc_quality"]["args"][0] == "doc-quality"
    assert manifest["mcp"]["command"] == "repo-quality-certifier-mcp"
    assert set(manifest["mcp"]["tools"]) == {
        "repo_quality_certifier_plan",
        "repo_quality_certifier_doc_quality",
    }
    assert (manifest_path.parent / "SKILL.md").exists()
