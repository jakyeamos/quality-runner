from __future__ import annotations

from pathlib import Path

from quality_runner.fleet.long_running_tasks import assess_long_running_tasks


def test_long_running_task_requires_explicit_qualification(tmp_path: Path) -> None:
    (tmp_path / "fleet_crawler.py").write_text(
        "def crawl_everything():\n    return list(range(1000))\n",
        encoding="utf-8",
    )

    result = assess_long_running_tasks(tmp_path)

    assert result["long_running_task_observability"]["status"] == "not_applicable"
    assert result["long_running_task_optimization"]["status"] == "not_applicable"


def test_annotation_example_inside_string_does_not_qualify_task(tmp_path: Path) -> None:
    (tmp_path / "docs_example.py").write_text(
        'EXAMPLE = "# quality-runner: long-running-task id=example"\n',
        encoding="utf-8",
    )

    result = assess_long_running_tasks(tmp_path)

    assert result["long_running_task_observability"]["status"] == "not_applicable"
    assert result["long_running_task_optimization"]["status"] == "not_applicable"


def test_annotated_long_running_task_reports_both_missing_standards(tmp_path: Path) -> None:
    (tmp_path / "worker.py").write_text(
        "# quality-runner: long-running-task id=full-preview\n"
        "def build_preview(rows):\n"
        "    return [render(row) for row in rows]\n",
        encoding="utf-8",
    )

    result = assess_long_running_tasks(tmp_path)

    assert result["long_running_task_observability"]["score"] == 0
    assert result["long_running_task_observability"]["status"] == "missing"
    assert result["long_running_task_optimization"]["score"] == 0
    assert result["long_running_task_optimization"]["status"] == "missing"


def test_annotated_long_running_task_passes_with_machine_progress_and_reuse(
    tmp_path: Path,
) -> None:
    (tmp_path / "worker.py").write_text(
        "# quality-runner: long-running-task id=full-preview\n"
        "def build_preview(rows, *, deadline, batch_size):\n"
        "    cached = materialize_once(rows)\n"
        "    for completed, batch in progress_batches(cached, batch_size):\n"
        "        emit_heartbeat({'status': 'running', 'completed': completed, 'total': len(cached), 'elapsed': timer.elapsed})\n",
        encoding="utf-8",
    )

    result = assess_long_running_tasks(tmp_path)

    assert result["long_running_task_observability"]["score"] == 4
    assert result["long_running_task_observability"]["status"] == "maintained"
    assert result["long_running_task_optimization"]["score"] == 4
    assert result["long_running_task_optimization"]["status"] == "maintained"


def test_workflow_timeout_is_concrete_qualification_and_partial_optimization(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / ".github" / "workflows" / "nightly.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  audit:\n    timeout-minutes: 20\n    steps:\n      - run: python audit.py\n",
        encoding="utf-8",
    )

    result = assess_long_running_tasks(tmp_path)

    assert result["long_running_task_observability"]["status"] == "missing"
    assert result["long_running_task_optimization"]["status"] == "partial"
