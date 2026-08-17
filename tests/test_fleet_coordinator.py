from __future__ import annotations

import shlex
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from quality_runner.fleet.coordinator import (
    coordinate_dynamic_result,
    dynamic_repository_watchdog_seconds,
)
from quality_runner.fleet.dynamic_commands import run_dynamic_command
from quality_runner.process_runner import run_shell_command


def test_dynamic_repository_watchdog_covers_bounded_command_budget() -> None:
    assert dynamic_repository_watchdog_seconds(30) == 450
    assert dynamic_repository_watchdog_seconds(120) == 1170


def test_coordinator_watchdog_returns_timeout_evidence_and_continues() -> None:
    def stalled_builder(**_arguments: object) -> dict[str, object]:
        time.sleep(1)
        return {"status": "passed"}

    result = coordinate_dynamic_result(
        build=stalled_builder,
        coordinator_watchdog_timeout_seconds=0.05,
        enabled=True,
        timeout_seconds=30,
        repository={
            "target_branch": {"branch": "dev", "head": "abc123"},
        },
    )

    assert result["status"] == "timeout"
    assert result["timeout_scope"] == "repository_dynamic"
    assert result["watchdog_timeout_seconds"] == 0.05
    assert result["target_branch"] == "dev"
    assert result["target_head"] == "abc123"
    assert result["implementation_allowed"] is False


def test_coordinator_watchdog_cleans_interrupted_dynamic_process_group(tmp_path: Path) -> None:
    terminated = tmp_path / "terminated"
    survived = tmp_path / "survived"
    script = f"""
import os
import signal
import time
from pathlib import Path

child = os.fork()
if child:
    os._exit(0)

def record_termination(*_args):
    Path({str(terminated)!r}).write_text("term\\n", encoding="utf-8")
    time.sleep(2)

signal.signal(signal.SIGTERM, record_termination)
time.sleep(2)
Path({str(survived)!r}).write_text("survived\\n", encoding="utf-8")
"""
    command = f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"

    def interrupted_builder(**_arguments: object) -> dict[str, object]:
        return run_dynamic_command(
            {"id": "tests", "command": command},
            tmp_path,
            30,
            runner=run_shell_command,
        )

    started = time.monotonic()
    result = coordinate_dynamic_result(
        build=interrupted_builder,
        coordinator_watchdog_timeout_seconds=0.5,
        enabled=True,
        timeout_seconds=30,
        repository={"target_branch": {"branch": "dev", "head": "abc123"}},
    )

    assert result["status"] == "timeout"
    assert result["timeout_scope"] == "repository_dynamic"
    assert time.monotonic() - started < 2
    assert terminated.is_file()
    assert not survived.exists()


def test_coordinator_watchdog_is_not_applied_to_static_only_audits() -> None:
    calls: list[dict[str, object]] = []

    def static_builder(**arguments: object) -> dict[str, object]:
        calls.append(arguments)
        return {"status": "not_selected"}

    result = coordinate_dynamic_result(
        build=static_builder,
        coordinator_watchdog_timeout_seconds=0.001,
        enabled=False,
        timeout_seconds=30,
    )

    assert result == {"status": "not_selected"}
    assert calls == [{"enabled": False, "timeout_seconds": 30}]


def test_coordinator_is_safe_in_parallel_worker_threads() -> None:
    def builder(**_arguments: object) -> dict[str, object]:
        return {"status": "passed"}

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _item: coordinate_dynamic_result(
                    build=builder,
                    enabled=True,
                    timeout_seconds=30,
                    repository={"target_branch": {"branch": "dev", "head": "abc123"}},
                ),
                range(2),
            )
        )

    assert results == [{"status": "passed"}, {"status": "passed"}]
