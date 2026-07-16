from __future__ import annotations

import json
from pathlib import Path


def _module(payload: dict[str, object], module_id: str) -> dict[str, object]:
    modules = payload["modules"]
    assert isinstance(modules, list)
    match = next(item for item in modules if item["id"] == module_id)
    assert isinstance(match, dict)
    return match


def test_module_status_marks_ui_and_native_similarity_as_core(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.module_status import build_module_status, validate_module_status

    source = "\n".join(
        [
            "export function renderAlpha(input: string) {",
            "  const normalized = input.trim();",
            "  if (normalized.length === 0) {",
            '    return "empty";',
            "  }",
            "  return normalized.toUpperCase();",
            "}",
        ]
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Panel.tsx").write_text(source + "\n", encoding="utf-8")
    scan = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "module-001"},
        config={"structural_scan": {"similarity_min_lines": 1}},
    )

    status = build_module_status(
        mode="run",
        profile="default",
        repo_scan={"repo_root": str(tmp_path), "provenance": {}},
        code_quality_scan=scan,
        capability_map={},
        standards_packet={"profile": "default"},
        security_scan={"settings": {"enabled": True}},
        config={},
    )

    assert validate_module_status(status)["passed"] is True
    assert _module(status, "similarity")["status"] == "enabled"
    assert _module(status, "ui-quality")["status"] == "enabled"
    assert _module(status, "ui-token-contract")["status"] == "not_run"
    assert _module(status, "release-readiness")["status"] == "not_applicable"
    assert status["summary"]["by_kind"]["core"]["enabled"] >= 5


def test_module_status_marks_ui_not_applicable_for_non_ui_repo(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.module_status import build_module_status

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "service.py").write_text(
        "def load_value(value):\n    return value.strip()\n", encoding="utf-8"
    )
    scan = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "module-002"},
        config={"structural_scan": {"similarity_min_lines": 1}},
    )
    status = build_module_status(
        mode="inspect",
        profile="default",
        repo_scan={"repo_root": str(tmp_path), "provenance": {}},
        code_quality_scan=scan,
    )

    assert _module(status, "ui-quality")["status"] == "not_applicable"
    assert _module(status, "similarity")["status"] == "enabled"


def test_explicit_ui_disable_is_visible_in_module_status(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan
    from quality_runner.module_status import build_module_status

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Panel.tsx").write_text(
        "export function Panel() {\n  return null;\n}\n", encoding="utf-8"
    )
    scan = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "module-003"},
        config={"structural_scan": {"disabled_rule_groups": ["ui_structural"]}},
    )
    status = build_module_status(
        mode="inspect",
        profile="default",
        repo_scan={"repo_root": str(tmp_path), "provenance": {}},
        code_quality_scan=scan,
    )

    assert scan["summary"]["ui_quality_status"] == "disabled"
    assert _module(status, "ui-quality")["status"] == "disabled"


def test_run_artifacts_expose_module_status(tmp_path: Path) -> None:
    from quality_runner.run_summary import build_run_summary
    from quality_runner.workflow import run_payload

    payload = run_payload(repo_root=tmp_path, run_id="module-artifacts")
    run_dir = tmp_path / ".quality-runner" / "runs" / "module-artifacts"
    repo_scan = json.loads((run_dir / "repo-scan.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "run-manifest.json").read_text(encoding="utf-8"))
    summary = build_run_summary(repo_root=tmp_path, run_id="module-artifacts", persist=False)

    assert payload["module_status"]["schema"] == "quality-runner-module-status-v0.1"
    assert repo_scan["module_status"] == payload["module_status"]
    assert manifest["module_status"] == payload["module_status"]
    assert summary["module_status"] == payload["module_status"]


def test_timeout_module_status_is_explicitly_not_run() -> None:
    from quality_runner.module_status import build_timeout_module_status

    status = build_timeout_module_status(
        mode="verify-gates", profile="release", reason="verify deadline exceeded"
    )

    assert _module(status, "repository-discovery")["status"] == "not_run"
    assert _module(status, "read-only-safety")["status"] == "enabled"
    assert _module(status, "ui-quality")["status"] == "not_run"
    assert _module(status, "release-readiness")["status"] == "not_run"
