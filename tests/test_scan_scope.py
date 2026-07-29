from __future__ import annotations

import json
import time
from pathlib import Path

from quality_runner import scan_scope
from quality_runner.workflow import inspect_payload


def _write(path: Path, content: str = "{}\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_large_protected_artifact_tree_is_not_recursively_estimated(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    artifact_root = tmp_path / ".quality-runner"
    for index in range(10_000):
        _write(artifact_root / "runs" / f"legacy-{index // 100:03d}" / f"artifact-{index}.json")
    _write(tmp_path / ".git" / "objects" / "legacy-object")
    _write(tmp_path / ".planning" / "phase-67.md", "# phase\n")
    _write(tmp_path / "artifacts" / "legacy-report.md", "# report\n")
    _write(tmp_path / "src" / "index.ts", "const source: any = {};\n")

    walked_paths: list[Path] = []
    original_walk = scan_scope.os.walk

    def tracking_walk(path: object, *args: object, **kwargs: object) -> object:
        walked_paths.append(Path(path).resolve())
        return original_walk(path, *args, **kwargs)

    monkeypatch.setattr(scan_scope.os, "walk", tracking_walk)
    started = time.monotonic()
    inspect_result = inspect_payload(
        tmp_path,
        run_id="artifact-regression",
        agent_review_mode="off",
    )
    elapsed = time.monotonic() - started
    artifact_paths = inspect_result["artifact_paths"]
    result = json.loads(Path(artifact_paths["code_quality_scan_json"]).read_text(encoding="utf-8"))

    assert elapsed < 2.0
    assert artifact_root.resolve() not in walked_paths
    assert (tmp_path / ".git").resolve() not in walked_paths
    assert (tmp_path / ".planning").resolve() not in walked_paths
    assert (tmp_path / "artifacts").resolve() not in walked_paths
    assert {item["path"] for item in result["accountability"]} == {"src/index.ts"}

    skipped = {item["path"]: item for item in result["skipped_files"]}
    for path in (".quality-runner", ".git", ".planning", "artifacts"):
        assert skipped[path]["estimated_text_files"] == 0
        assert skipped[path]["estimated_scan_seconds"] == 0.0
        assert skipped[path]["estimate_status"] == "not-estimated"
        assert skipped[path]["estimate_reason"] == "protected or excluded artifact directory"
    assert result["summary"]["skipped_estimated_scan_seconds"] == 0.0
    assert result["summary"]["skipped_unestimated_directories"] == 4
    assert result["summary"]["skipped_directory_estimate_status"] == "partial"
