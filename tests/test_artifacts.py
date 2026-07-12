from __future__ import annotations

import json
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


def test_artifact_namespace_helpers_reject_symlink_components(tmp_path: Path) -> None:
    from quality_runner.artifacts import existing_artifact_dir, prepare_artifact_dir

    external = tmp_path / "external"
    external.mkdir()
    cases = ((".quality-runner",), (".quality-runner", "runs"), (".quality-runner", "runs", "run"))
    for index, parts in enumerate(cases):
        repo = tmp_path / f"repo-{index}"
        repo.mkdir()
        if parts == (".quality-runner",):
            (repo / ".quality-runner").symlink_to(external, target_is_directory=True)
        elif parts == (".quality-runner", "runs"):
            (repo / ".quality-runner").mkdir()
            (repo / ".quality-runner" / "runs").symlink_to(external, target_is_directory=True)
        else:
            runs = repo / ".quality-runner" / "runs"
            runs.mkdir(parents=True)
            (runs / "run").symlink_to(external, target_is_directory=True)
        for helper in (prepare_artifact_dir, existing_artifact_dir):
            try:
                helper(repo, "run")
            except ValueError as error:
                assert str(error) == "artifact path component must not be a symlink"
            else:
                raise AssertionError(f"{helper.__name__} accepted a symlinked namespace")


def test_artifact_text_file_rejects_symlink_leaf(tmp_path: Path) -> None:
    from quality_runner.artifacts import artifact_text_file, prepare_artifact_dir

    run_dir = prepare_artifact_dir(tmp_path, "run")
    external = tmp_path / "external.md"
    external.write_text("secret\n", encoding="utf-8")
    (run_dir / "agent-handoff.md").symlink_to(external)

    try:
        artifact_text_file(tmp_path, "run", "agent-handoff.md")
    except ValueError as error:
        assert str(error) == "artifact file must not be a symlink"
    else:
        raise AssertionError("artifact_text_file accepted a symlink leaf")

    assert external.read_text(encoding="utf-8") == "secret\n"


def test_write_text_rejects_nested_symlink_ancestor_without_external_write(tmp_path: Path) -> None:
    from quality_runner.artifacts import write_text

    external = tmp_path / "external"
    (external / "nested").mkdir(parents=True)
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(external, target_is_directory=True)
    target = linked_parent / "nested" / "handoff.md"

    try:
        write_text(target, "should not escape\n")
    except ValueError as error:
        assert str(error) == "artifact path component must not be a symlink"
    else:
        raise AssertionError("write_text followed a symlinked ancestor")

    assert not (external / "nested" / "handoff.md").exists()
