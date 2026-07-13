from __future__ import annotations

import json
import os
from pathlib import Path


def test_artifact_dir_uses_quality_runner_namespace(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    path = artifact_dir(tmp_path, "run-001")

    assert path == tmp_path / ".quality-runner" / "runs" / "run-001"


def test_artifact_dir_rejects_absolute_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "/tmp/run-001")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted an absolute run ID")


def test_artifact_dir_rejects_parent_traversal_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "../escape")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a parent traversal run ID")


def test_artifact_dir_rejects_empty_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted an empty run ID")


def test_artifact_dir_rejects_separator_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "nested/run")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a separator run ID")


def test_artifact_dir_rejects_backslash_separator_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "nested\\run")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a backslash separator run ID")


def test_artifact_dir_rejects_windows_absolute_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "C:\\temp\\run")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a Windows absolute run ID")


def test_artifact_dir_rejects_windows_drive_relative_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "C:run")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a Windows drive-relative run ID")


def test_artifact_dir_rejects_dot_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, ".")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a dot run ID")


def test_artifact_dir_rejects_parent_run_ids(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_dir

    try:
        artifact_dir(tmp_path, "..")
    except ValueError as error:
        assert str(error) == "run_id must be a non-empty single path segment"
    else:
        raise AssertionError("artifact_dir accepted a parent run ID")


def test_write_json_creates_parent_and_stable_json(tmp_path: Path) -> None:
    from quality_runner.artifacts import write_json

    path = write_json(tmp_path / "nested" / "payload.json", {"b": 2, "a": 1})

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert path.read_text(encoding="utf-8") == '{\n  "a": 1,\n  "b": 2\n}\n'


def test_write_json_rejects_symlink_leaf_without_external_write(tmp_path: Path) -> None:
    from quality_runner.artifacts import write_json

    external = tmp_path / "external.json"
    external.write_text("sentinel\n", encoding="utf-8")
    target = tmp_path / "nested" / "payload.json"
    target.parent.mkdir()
    target.symlink_to(external)

    try:
        write_json(target, {"changed": True})
    except ValueError as error:
        assert str(error) == "artifact file must not be a symlink"
    else:
        raise AssertionError("write_json accepted a symlink leaf")

    assert external.read_text(encoding="utf-8") == "sentinel\n"


def test_write_text_creates_parent_returns_path_and_writes_exact_content(tmp_path: Path) -> None:
    from quality_runner.artifacts import write_text

    target = tmp_path / "nested" / "report.txt"
    path = write_text(target, "line 1\nline 2")

    assert path == target
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "line 1\nline 2"


def test_run_artifacts_apply_configured_redaction_before_persisting(tmp_path: Path) -> None:
    from quality_runner.artifacts import prepare_artifact_dir, write_json, write_text

    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.artifacts]",
                'redact_patterns = ["TOP-SECRET-[A-Z0-9]+"]',
                'redact_replacement = "<redacted>"',
            ]
        ),
        encoding="utf-8",
    )
    run_dir = prepare_artifact_dir(tmp_path, "redaction-run")

    write_json(run_dir / "report.json", {"evidence": "TOP-SECRET-123"})
    write_text(run_dir / "report.md", "Evidence: TOP-SECRET-456\n")

    assert "TOP-SECRET" not in (run_dir / "report.json").read_text(encoding="utf-8")
    assert (run_dir / "report.json").read_text(encoding="utf-8").count("<redacted>") == 1
    assert (run_dir / "report.md").read_text(encoding="utf-8") == "Evidence: <redacted>\n"


def test_cleanup_artifacts_previews_and_deletes_by_run_count(tmp_path: Path) -> None:
    from quality_runner.artifacts import cleanup_artifacts

    (tmp_path / ".quality-runner.toml").write_text(
        "[quality_runner.artifacts]\nretention_runs = 2\n",
        encoding="utf-8",
    )
    runs_dir = tmp_path / ".quality-runner" / "runs"
    for index, run_id in enumerate(("old", "middle", "new")):
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "run-manifest.json").write_text("{}\n", encoding="utf-8")
        timestamp = 100 + index
        os.utime(run_dir, (timestamp, timestamp))

    preview = cleanup_artifacts(tmp_path, apply=False, now=200)
    assert preview["status"] == "dry-run"
    assert preview["would_delete_run_ids"] == ["old"]
    assert (runs_dir / "old").exists()

    result = cleanup_artifacts(tmp_path, apply=True, now=200)
    assert result["status"] == "pruned"
    assert result["deleted_run_ids"] == ["old"]
    assert not (runs_dir / "old").exists()
    assert (runs_dir / "middle").exists()
    assert (runs_dir / "new").exists()
