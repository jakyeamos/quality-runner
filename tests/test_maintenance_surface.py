from __future__ import annotations

import json
import subprocess
import sys
from importlib import resources
from pathlib import Path

from quality_runner.config import load_repo_config
from quality_runner.maintenance_surface import (
    MAINTENANCE_SURFACE_SCHEMA,
    REGRESSION_PROOF_SCHEMA,
    maintenance_surface_payload,
    render_maintenance_surface_markdown,
)
from quality_runner.maintenance_surface_config_parse import parse_maintenance_surface_section

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init(repo: Path) -> None:
    _git(repo, "init", "-q")


def _commit(repo: Path, message: str = "fixture") -> str:
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.email=quality-runner@example.com",
        "-c",
        "user.name=Quality Runner",
        "commit",
        "-m",
        message,
    )
    return _git(repo, "rev-parse", "HEAD")


def test_worktree_delta_is_descriptive_and_reviews_residual_removal(tmp_path: Path) -> None:
    _init(tmp_path)
    source = tmp_path / "src"
    tests = tmp_path / "tests"
    source.mkdir()
    tests.mkdir()
    (source / "legacy_feature.py").write_text(
        "def legacy_feature():\n    return 'legacy'\n", encoding="utf-8"
    )
    (tests / "test_legacy.py").write_text(
        "from src.legacy_feature import legacy_feature\n\n"
        "def test_legacy():\n    assert legacy_feature() == 'legacy'\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "fixture", "dependencies": {}}) + "\n", encoding="utf-8"
    )
    base = _commit(tmp_path)

    (source / "legacy_feature.py").unlink()
    (source / "public_api.py").write_text(
        "def public_status():\n    return 'ready'\n", encoding="utf-8"
    )
    (tests / "test_public_api.py").write_text(
        "def test_public_status():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "fixture", "dependencies": {"httpx": "1.0.0"}}) + "\n",
        encoding="utf-8",
    )

    payload = maintenance_surface_payload(
        tmp_path,
        behavior_added=("Expose repository readiness",),
        behavior_removed=("Legacy status helper",),
        consolidated_concepts=("repository readiness",),
    )

    assert payload["schema"] == MAINTENANCE_SURFACE_SCHEMA
    assert payload["status"] == "review_required"
    assert payload["provenance"] == {
        "requested_base": "HEAD",
        "requested_head": "WORKTREE",
        "base_commit": base,
        "head_commit": base,
        "comparison_base_commit": base,
        "working_tree": True,
    }
    delta = payload["maintenance_surface_delta"]
    assert delta["lines"]["production"]["added"] == 2
    assert delta["lines"]["test"]["added"] == 2
    assert delta["dependencies"] == [{"name": "httpx", "manifest": "package.json"}]
    assert delta["public_surface_candidates"] == [
        {"path": "src/public_api.py", "evidence": "def public_status():"}
    ]
    assert delta["concepts_consolidated"] == ["repository readiness"]
    assert any(
        item["id"] == "vertical-slice-removal"
        and any("tests/test_legacy.py" in evidence for evidence in item["evidence"])
        for item in payload["observations"]
    )


def test_configured_owner_compatibility_and_verified_regression_can_be_ready(
    tmp_path: Path,
) -> None:
    _init(tmp_path)
    source = tmp_path / "src"
    source.mkdir()
    (source / "status.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner.maintenance_surface]\n"
        "enabled = true\n\n"
        "[[quality_runner.maintenance_surface.behavior_owners]]\n"
        'id = "status"\n'
        'owner = "src/status.py"\n'
        'paths = ["src/status.py"]\n\n'
        "[[quality_runner.maintenance_surface.compatibility]]\n"
        'id = "legacy-status"\n'
        'consumer = "desktop 1.x"\n'
        'owner = "src/status.py"\n'
        'behavior = "preserve old field"\n'
        'removal_condition = "desktop 1.x unsupported"\n'
        'paths = ["src/status.py"]\n',
        encoding="utf-8",
    )
    _commit(tmp_path)
    (source / "status.py").write_text(
        "def public_status():\n    return 'legacy compatibility'\n", encoding="utf-8"
    )
    proof = tmp_path / "regression-proof.json"
    proof.write_text(
        json.dumps(
            {
                "schema": REGRESSION_PROOF_SCHEMA,
                "status": "verified",
                "test": "pytest tests/test_status.py::test_status",
                "defective_revision": "abc123",
                "defective_result": "failed",
                "fixed_revision": "def456",
                "fixed_result": "passed",
            }
        ),
        encoding="utf-8",
    )

    payload = maintenance_surface_payload(tmp_path, regression_proof_path=proof)

    assert payload["status"] == "ready"
    assert payload["contracts"]["status"] == "configured"
    assert payload["contracts"]["behavior_owners"][0]["changed_paths"] == ["src/status.py"]
    assert payload["contracts"]["compatibility"][0]["changed_paths"] == ["src/status.py"]
    assert payload["regression_proof"]["status"] == "verified"
    assert payload["observations"] == []


def test_invalid_contract_and_unavailable_proof_remain_explicit(tmp_path: Path) -> None:
    _init(tmp_path)
    (tmp_path / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner.maintenance_surface]\n"
        "enabled = true\n\n"
        "[[quality_runner.maintenance_surface.compatibility]]\n"
        'id = "missing-fields"\n'
        'paths = ["module.py"]\n',
        encoding="utf-8",
    )
    _commit(tmp_path)
    (tmp_path / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    proof = tmp_path / "unavailable.json"
    proof.write_text(
        json.dumps(
            {
                "schema": REGRESSION_PROOF_SCHEMA,
                "status": "unavailable",
                "reason": "defective environment was retired",
            }
        ),
        encoding="utf-8",
    )

    config = load_repo_config(tmp_path)
    payload = maintenance_surface_payload(tmp_path, regression_proof_path=proof)

    assert any(
        "maintenance_surface.compatibility[0]" in item["message"] for item in config["warnings"]
    )
    assert payload["status"] == "blocked"
    assert payload["contracts"]["status"] == "invalid"
    assert payload["regression_proof"]["status"] == "unavailable"
    assert any(item["id"] == "regression-proof-unavailable" for item in payload["observations"])


def test_cli_writes_json_and_markdown_handoff(tmp_path: Path) -> None:
    _init(tmp_path)
    (tmp_path / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    _commit(tmp_path)
    (tmp_path / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    output = tmp_path / "evidence" / "maintenance.json"
    handoff = tmp_path / "evidence" / "maintenance.md"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quality_runner",
            "maintenance-surface",
            str(tmp_path),
            "--behavior-added",
            "Expose status",
            "--output",
            str(output),
            "--handoff-output",
            str(handoff),
            "--json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert output.is_file()
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == MAINTENANCE_SURFACE_SCHEMA
    assert "## Maintenance surface" in handoff.read_text(encoding="utf-8")
    assert "Expose status" in handoff.read_text(encoding="utf-8")


def test_payload_writer_and_renderer_are_exercised_without_a_subprocess(tmp_path: Path) -> None:
    _init(tmp_path)
    (tmp_path / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    _commit(tmp_path)
    (tmp_path / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    output = tmp_path / "evidence" / "maintenance.json"
    handoff = tmp_path / "evidence" / "maintenance.md"

    payload = maintenance_surface_payload(
        tmp_path,
        behavior_added=("Expose status",),
        behavior_removed=("Remove legacy status",),
        consolidated_concepts=("status",),
        output_path=output,
        handoff_output_path=handoff,
    )
    rendered = render_maintenance_surface_markdown(payload)

    assert payload["output_path"] == str(output)
    assert payload["handoff_output_path"] == str(handoff)
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == MAINTENANCE_SURFACE_SCHEMA
    assert handoff.read_text(encoding="utf-8") == rendered
    assert "Remove legacy status" in rendered
    assert "Concepts consolidated" in rendered


def test_maintenance_surface_config_parser_keeps_invalid_contracts_explicit() -> None:
    warnings: list[dict[str, str]] = []
    parsed = parse_maintenance_surface_section(
        {
            "enabled": "yes",
            "behavior_owners": "not-a-list",
            "compatibility": [
                "not-a-table",
                {"id": "duplicate", "paths": ["src/status.py"]},
                {"id": "duplicate", "paths": ["src/status.py"]},
            ],
        },
        warnings,
    )

    assert "enabled" not in parsed
    assert parsed["behavior_owners"] == []
    assert parsed["compatibility"] == []
    assert len(warnings) == 5
    assert all(item["code"] == "invalid_quality_runner_config_field" for item in warnings)


def test_invalid_regression_proof_blocks_claim_and_schemas_are_packaged(tmp_path: Path) -> None:
    _init(tmp_path)
    (tmp_path / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    _commit(tmp_path)
    (tmp_path / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    proof = tmp_path / "invalid-proof.json"
    proof.write_text(
        json.dumps(
            {
                "schema": REGRESSION_PROOF_SCHEMA,
                "status": "verified",
                "test": "pytest tests/test_module.py",
                "defective_revision": "abc123",
                "defective_result": "passed",
                "fixed_revision": "def456",
                "fixed_result": "passed",
            }
        ),
        encoding="utf-8",
    )

    payload = maintenance_surface_payload(tmp_path, regression_proof_path=proof)
    maintenance_schema = resources.files("quality_runner").joinpath(
        "schemas/maintenance-surface.schema.json"
    )
    proof_schema = resources.files("quality_runner").joinpath(
        "schemas/regression-proof.schema.json"
    )

    assert payload["status"] == "blocked"
    assert payload["regression_proof"]["status"] == "invalid"
    assert json.loads(maintenance_schema.read_text(encoding="utf-8"))["$id"] == (
        MAINTENANCE_SURFACE_SCHEMA
    )
    assert json.loads(proof_schema.read_text(encoding="utf-8"))["$id"] == REGRESSION_PROOF_SCHEMA


def test_revision_comparison_records_requested_heads_and_merge_base(tmp_path: Path) -> None:
    _init(tmp_path)
    (tmp_path / "module.py").write_text("VALUE = 'base'\n", encoding="utf-8")
    merge_base = _commit(tmp_path, "base")
    (tmp_path / "target.py").write_text("TARGET = True\n", encoding="utf-8")
    target_commit = _commit(tmp_path, "target")
    _git(tmp_path, "branch", "target")
    _git(tmp_path, "switch", "-c", "feature", merge_base)
    (tmp_path / "feature.py").write_text("FEATURE = True\n", encoding="utf-8")
    feature_commit = _commit(tmp_path, "feature")

    payload = maintenance_surface_payload(tmp_path, base_ref="target", head_ref="feature")

    assert payload["provenance"] == {
        "requested_base": "target",
        "requested_head": "feature",
        "base_commit": target_commit,
        "head_commit": feature_commit,
        "comparison_base_commit": merge_base,
        "working_tree": False,
    }
    assert payload["maintenance_surface_delta"]["files"]["paths"] == [
        {
            "path": "feature.py",
            "old_path": None,
            "status": "added",
            "added": 1,
            "removed": 0,
            "category": "production",
            "untracked": False,
        }
    ]
