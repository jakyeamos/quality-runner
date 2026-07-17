from __future__ import annotations

import json
import time
from io import StringIO
from pathlib import Path

from quality_runner.progress import ProgressReporter
from test_support.quality_runner_fixtures import write_js_fixture


def test_progress_reporter_emits_phases_heartbeats_and_completion() -> None:
    stream = StringIO()

    with ProgressReporter("run", stream=stream, interval_seconds=0.01) as progress:
        progress.phase("code-quality", "scanning selected skill packs")
        time.sleep(0.04)
        progress.finish("planned")

    output = stream.getvalue()
    assert "event=started" in output
    assert "event=phase command=run phase=code-quality" in output
    assert "event=heartbeat command=run phase=code-quality" in output
    assert "event=complete command=run phase=code-quality" in output
    assert "status=planned" in output


def test_cli_json_keeps_stdout_machine_readable_and_reports_progress_on_stderr(
    tmp_path: Path,
    capsys,
) -> None:
    from quality_runner.cli import main

    write_js_fixture(tmp_path)
    assert main(["run", str(tmp_path), "--run-id", "progress-run", "--json"]) == 0

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["run_id"] == "progress-run"
    assert "event=phase command=run phase=discovery" in captured.err
    assert "event=phase command=run phase=code-quality" in captured.err
    assert "event=complete command=run" in captured.err


def test_cli_no_progress_suppresses_diagnostic_stream(tmp_path: Path, capsys) -> None:
    from quality_runner.cli import main

    write_js_fixture(tmp_path)
    assert main(["run", str(tmp_path), "--run-id", "quiet-run", "--json", "--no-progress"]) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out)["run_id"] == "quiet-run"
    assert "[quality-runner]" not in captured.err
