from __future__ import annotations

import shutil
from pathlib import Path


def test_fixture_corpus_dogfood_contract(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    corpus_root = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"
    expected = {
        "complete-js": "clean",
        "mature-mixed": "planned",
        "partial-js": "planned",
        "python-empty": "planned",
    }

    for fixture_name, status in expected.items():
        target = tmp_path / fixture_name
        shutil.copytree(corpus_root / fixture_name, target)

        payload = run_payload(repo_root=target, run_id=f"{fixture_name}-dogfood")

        assert payload["status"] == status
        assert Path(payload["artifact_paths"]["run_manifest_json"]).exists()
        assert Path(payload["artifact_paths"]["agent_handoff_md"]).exists()


def test_quality_runner_self_audit_excludes_fixture_workspaces_by_default() -> None:
    from quality_runner.discovery import inspect_repo

    repo_root = Path(__file__).resolve().parents[1]

    scan = inspect_repo(repo_root, run_id="self-audit-scan-exclusions")

    workspace_paths = {workspace["path"] for workspace in scan["workspaces"]}
    assert all(not path.startswith("fixtures/") for path in workspace_paths)
