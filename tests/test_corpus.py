from __future__ import annotations

import shutil
from pathlib import Path


def test_fixture_corpus_dogfood_contract(tmp_path: Path) -> None:
    from quality_runner.workflow import run_payload

    corpus_root = Path(__file__).resolve().parents[1] / "fixtures" / "corpus"
    expected = {
        "complete-js": "clean",
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
