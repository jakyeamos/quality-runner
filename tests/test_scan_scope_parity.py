from __future__ import annotations

import json
from pathlib import Path

from quality_runner.discovery import inspect_repo
from quality_runner.scan_scope_resolver import artifact_scan_scope
from quality_runner.workflow import inspect_payload


def test_compatibility_inspect_loads_repo_config_and_excludes_configured_paths(
    tmp_path: Path,
) -> None:
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner]",
                'scan_exclusions = [".agents", "tests", "e2e", "__tests__", ".design-sync/previews/**"]',
                "",
                "[quality_runner.scan_exclusions_by_module]",
                'code_quality = ["generated-output/**"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('source')\n", encoding="utf-8")
    for relative_path in (
        ".planning/tests/planning.py",
        ".agents/agent.py",
        "tests/test_source.py",
        "e2e/browser.ts",
        "__tests__/component.ts",
        ".design-sync/previews/preview.ts",
    ):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("eval(input)\n", encoding="utf-8")
    generated = tmp_path / "generated-output" / "secrets.js"
    generated.parent.mkdir()
    generated.write_text(
        'const apiKey = "example-placeholder-not-a-real-secret";\n', encoding="utf-8"
    )

    result = inspect_payload(tmp_path, run_id="scope-parity", agent_review_mode="off")
    artifact_paths = result["artifact_paths"]
    repo_scan = _read_json(artifact_paths["repo_scan_json"])
    code_quality = _read_json(artifact_paths["code_quality_scan_json"])
    security = _read_json(artifact_paths["security_scan_json"])

    repo_scope = repo_scan["scan_scope"]
    code_scope = code_quality["scan_scope"]
    security_scope = security["scan_scope"]
    assert repo_scope["status"] == "available"
    assert code_scope["status"] == "available"
    assert security_scope["status"] == "available"
    assert repo_scope["config_path"] == ".quality-runner.toml"
    assert repo_scope["config_sha256"].startswith("sha256:")
    assert ".planning" in repo_scope["effective_scan_exclusions"]
    assert ".agents" in repo_scope["effective_scan_exclusions"]
    assert "generated-output/**" in code_scope["effective_scan_exclusions"]
    assert "generated-output/**" not in security_scope["effective_scan_exclusions"]
    assert (
        len({repo_scope["fingerprint"], code_scope["fingerprint"], security_scope["fingerprint"]})
        == 1
    )
    assert repo_scan["included_file_count"]["code_quality"] == code_quality["included_file_count"]
    assert repo_scan["cache"]["status"] == "disabled"
    assert code_quality["included_file_count"] == code_quality["summary"]["total_files"]
    assert security["included_file_count"] > 0
    assert code_scope["cache"]["status"] == "disabled"
    assert code_quality["provenance"]["quality_runner_version"]

    code_paths = {item["path"] for item in code_quality["accountability"]}
    assert "src/main.py" in code_paths
    assert not any(
        path.startswith((".planning/", ".agents/", "tests/", "e2e/", "__tests__/"))
        for path in code_paths
    )
    assert "generated-output/secrets.js" not in code_paths
    assert any(item["file"] == "generated-output/secrets.js" for item in security["candidates"])


def test_inspect_repo_resolves_config_when_callers_omit_it(tmp_path: Path) -> None:
    (tmp_path / ".quality-runner.toml").write_text(
        '[quality_runner]\nscan_exclusions = ["private-fixtures/**"]\n',
        encoding="utf-8",
    )

    scan = inspect_repo(tmp_path, run_id="direct-config-resolution")

    assert "private-fixtures/**" in scan["scan_exclusions"]
    assert scan["scan_scope"]["effective_scan_exclusions"] == scan["scan_exclusions"]
    assert scan["scan_scope"]["status"] == "available"


def test_artifact_scope_marks_non_comparable_scope_unavailable(tmp_path: Path) -> None:
    scan = inspect_repo(tmp_path, run_id="scope-mismatch")

    scope = artifact_scan_scope(
        scan,
        repo_root=tmp_path,
        config={},
        module="code_quality",
        scan_exclusions=["not-the-resolved-scope/**"],
        included_file_count=1,
    )

    assert scope["status"] == "unavailable"
    assert "differ from the resolved scope" in scope["reason"]


def _read_json(path: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload
