from __future__ import annotations

from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_python_performance_rules_find_queries_and_sync_work_in_async_loops(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "backend" / "startup_tasks.py",
        """async def refresh_all(conn, roster_ids):
    for roster_id in roster_ids:
        conn.execute("SELECT * FROM rosters WHERE roster_id = ?", [roster_id])
    refresh_global_sources(conn)
""",
    )

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "python-performance"},
        config={},
        persist_cache=False,
    )

    findings = {finding["rule_id"]: finding for finding in result["findings"]}
    assert findings["python-query-in-loop"]["line"] == 3
    assert findings["python-blocking-call-in-async"]["line"] == 3
    assert findings["python-sync-work-call-in-async"]["line"] == 4


def test_python_performance_rules_accept_awaited_and_worker_isolated_work(
    tmp_path: Path,
) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "backend" / "startup_tasks.py",
        """import asyncio

async def refresh_all(conn, roster_ids):
    rows = await conn.execute("SELECT roster_id FROM rosters")
    for row in rows:
        consume(row)
    await asyncio.to_thread(refresh_global_sources, conn)
""",
    )

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "python-performance-safe"},
        config={},
        persist_cache=False,
    )

    rules = {finding["rule_id"] for finding in result["findings"]}
    assert "python-query-in-loop" not in rules
    assert "python-blocking-call-in-async" not in rules
    assert "python-sync-work-call-in-async" not in rules


def test_python_performance_rules_ignore_query_used_to_create_iterator(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "backend" / "report.py",
        """def render(conn):
    for row in conn.execute("SELECT roster_id FROM rosters"):
        consume(row)
""",
    )

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "python-performance-iterator"},
        config={},
        persist_cache=False,
    )

    rules = {finding["rule_id"] for finding in result["findings"]}
    assert "python-query-in-loop" not in rules


def test_python_performance_rules_fail_open_for_invalid_python(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(tmp_path / "backend" / "broken.py", "async def incomplete(\n")

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "python-performance-invalid"},
        config={},
        persist_cache=False,
    )

    rules = {finding["rule_id"] for finding in result["findings"]}
    assert "python-query-in-loop" not in rules
    assert "python-blocking-call-in-async" not in rules
    assert "python-sync-work-call-in-async" not in rules


def test_python_performance_rules_ignore_test_fixture_database_loops(tmp_path: Path) -> None:
    from quality_runner.code_quality import create_code_quality_scan

    _write(
        tmp_path / "tests" / "test_seed.py",
        """async def seed(conn, roster_ids):
    for roster_id in roster_ids:
        conn.execute("INSERT INTO rosters VALUES (?)", [roster_id])
""",
    )
    _write(
        tmp_path / "backend" / "tests" / "conftest.py",
        """async def seed_more(conn, roster_ids):
    for roster_id in roster_ids:
        conn.execute("INSERT INTO rosters VALUES (?)", [roster_id])
""",
    )

    result = create_code_quality_scan(
        tmp_path,
        scan={"run_id": "python-performance-test-fixture"},
        config={},
        persist_cache=False,
    )

    rules = {finding["rule_id"] for finding in result["findings"]}
    assert "python-query-in-loop" not in rules
    assert "python-blocking-call-in-async" not in rules
