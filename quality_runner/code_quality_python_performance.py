from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from quality_runner.code_quality_findings import finding as build_finding
from quality_runner.code_quality_paths import is_test_file, verification_for_path

_DATABASE_METHODS = frozenset(
    {
        "execute",
        "executemany",
        "fetch",
        "fetchall",
        "fetchone",
        "query",
        "scalar",
        "scalars",
        "sql",
    }
)
_DATABASE_RECEIVERS = frozenset(
    {"conn", "connection", "cursor", "database", "db", "duckdb", "engine", "repo", "session"}
)
_SYNC_WORK_PREFIXES = ("backfill_", "ingest_", "migrate_", "rebuild_", "refresh_")
_KNOWN_BLOCKING_CALLS = frozenset(
    {
        "requests.delete",
        "requests.get",
        "requests.head",
        "requests.patch",
        "requests.post",
        "requests.put",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.popen",
        "subprocess.run",
        "time.sleep",
        "urllib.request.urlopen",
    }
)


@dataclass(frozen=True)
class PythonPerformanceRisk:
    kind: str
    line: int
    evidence: str


def python_performance_risks(text: str, lines: list[str]) -> list[PythonPerformanceRisk]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    visitor = _PythonPerformanceVisitor(lines)
    visitor.visit(tree)
    return visitor.risks


def python_performance_signals(text: str) -> set[str]:
    risks = python_performance_risks(text, text.splitlines())
    signals: set[str] = set()
    if any(risk.kind == "query-in-loop" for risk in risks):
        signals.update({"database", "performance", "scaling"})
    if any(risk.kind in {"blocking-call-in-async", "sync-work-call-in-async"} for risk in risks):
        signals.update({"concurrency", "io", "performance"})
    return signals


def python_repository_performance_signals(relative_path: str, text: object) -> set[str]:
    if _is_performance_test_path(relative_path):
        return set()
    signals: set[str] = (
        python_performance_signals(text) if isinstance(text, str) and text else set()
    )
    path_tokens = set(re.findall(r"[a-z0-9]+", relative_path.lower()))
    if "backend" in path_tokens and path_tokens & {
        "backfill",
        "database",
        "ingest",
        "lifespan",
        "migration",
        "refresh",
        "startup",
    }:
        signals.update({"io", "performance"})
    return signals


def python_performance_findings(
    relative_path: str,
    text: str,
    lines: list[str],
) -> list[dict[str, Any]]:
    if Path(relative_path).suffix.lower() != ".py" or _is_performance_test_path(relative_path):
        return []
    findings: list[dict[str, Any]] = []
    for risk in python_performance_risks(text, lines):
        if risk.kind == "query-in-loop":
            findings.append(
                build_finding(
                    category="speed",
                    severity="observation",
                    confidence="medium",
                    file=relative_path,
                    line=risk.line,
                    rule_id="python-query-in-loop",
                    evidence=risk.evidence,
                    expected_improvement=(
                        "Batch or prefetch database work outside the loop, or document the bounded "
                        "workload and required sequencing."
                    ),
                    risk=(
                        "Per-item database access can create N+1 query growth and hold a writer or "
                        "request path longer than expected."
                    ),
                    verification=verification_for_path(relative_path),
                    remediation_bucket="performance and batching improvements",
                )
            )
        elif risk.kind == "blocking-call-in-async":
            findings.append(
                build_finding(
                    category="speed",
                    severity="observation",
                    confidence="medium",
                    file=relative_path,
                    line=risk.line,
                    rule_id="python-blocking-call-in-async",
                    evidence=risk.evidence,
                    expected_improvement=(
                        "Use an awaitable client or isolate synchronous I/O in a bounded worker "
                        "thread, then verify request-path responsiveness."
                    ),
                    risk=(
                        "Synchronous database, network, process, or sleep work inside an async "
                        "function can block its event loop and inflate tail latency."
                    ),
                    verification=verification_for_path(relative_path),
                    remediation_bucket="performance and concurrency improvements",
                )
            )
        else:
            findings.append(
                build_finding(
                    category="speed",
                    severity="observation",
                    confidence="low",
                    file=relative_path,
                    line=risk.line,
                    rule_id="python-sync-work-call-in-async",
                    evidence=risk.evidence,
                    expected_improvement=(
                        "Confirm the work is non-blocking or move it behind asyncio.to_thread, an "
                        "executor, or an explicitly asynchronous implementation."
                    ),
                    risk=(
                        "Refresh, rebuild, ingest, migration, or backfill work invoked without await "
                        "may monopolize an async lifecycle or request path."
                    ),
                    verification=verification_for_path(relative_path),
                    remediation_bucket="performance and concurrency improvements",
                )
            )
    return findings


class _PythonPerformanceVisitor(ast.NodeVisitor):
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self._async_depth: int = 0
        self._await_depth: int = 0
        self._loop_depth: int = 0
        self.risks: list[PythonPerformanceRisk] = []

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        prior: tuple[int, int, int] = (
            self._async_depth,
            self._await_depth,
            self._loop_depth,
        )
        self._async_depth, self._await_depth, self._loop_depth = 1, 0, 0
        self.generic_visit(node)
        self._async_depth, self._await_depth, self._loop_depth = prior

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        prior: tuple[int, int, int] = (
            self._async_depth,
            self._await_depth,
            self._loop_depth,
        )
        self._async_depth, self._await_depth, self._loop_depth = 0, 0, 0
        self.generic_visit(node)
        self._async_depth, self._await_depth, self._loop_depth = prior

    def visit_Lambda(self, node: ast.Lambda) -> None:
        prior: tuple[int, int, int] = (
            self._async_depth,
            self._await_depth,
            self._loop_depth,
        )
        self._async_depth, self._await_depth, self._loop_depth = 0, 0, 0
        self.generic_visit(node)
        self._async_depth, self._await_depth, self._loop_depth = prior

    def visit_Await(self, node: ast.Await) -> None:
        self._await_depth += 1
        self.generic_visit(node)
        self._await_depth -= 1

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.target)
        self.visit(node.iter)
        self._visit_repeated_statements(node.body)
        self._visit_statements(node.orelse)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.visit(node.target)
        self.visit(node.iter)
        self._visit_repeated_statements(node.body)
        self._visit_statements(node.orelse)

    def visit_While(self, node: ast.While) -> None:
        self._loop_depth += 1
        self.visit(node.test)
        self._visit_statements(node.body)
        self._loop_depth -= 1
        self._visit_statements(node.orelse)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = _call_name(node.func)
        database_call = _is_database_call(call_name)
        if self._loop_depth > 0 and database_call:
            self._add_risk("query-in-loop", node)
        if self._async_depth > 0 and self._await_depth == 0:
            if database_call or call_name in _KNOWN_BLOCKING_CALLS:
                self._add_risk("blocking-call-in-async", node)
            elif _is_sync_work_call(call_name):
                self._add_risk("sync-work-call-in-async", node)
        self.generic_visit(node)

    def _visit_repeated_statements(self, statements: list[ast.stmt]) -> None:
        self._loop_depth += 1
        self._visit_statements(statements)
        self._loop_depth -= 1

    def _visit_statements(self, statements: list[ast.stmt]) -> None:
        for statement in statements:
            self.visit(statement)

    def _add_risk(self, kind: str, node: ast.Call) -> None:
        line_number = int(getattr(node, "lineno", 1))
        evidence = self._lines[line_number - 1] if 0 < line_number <= len(self._lines) else ""
        self.risks.append(
            PythonPerformanceRisk(kind=kind, line=line_number, evidence=evidence.strip())
        )


def _is_performance_test_path(relative_path: str) -> bool:
    path = Path(relative_path)
    return is_test_file(relative_path) or "tests" in path.parts or path.name == "conftest.py"


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id.lower()
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr.lower()}" if parent else node.attr.lower()
    return ""


def _is_database_call(call_name: str) -> bool:
    parts = [_normalized_identifier(part) for part in call_name.split(".") if part]
    if not parts or parts[-1] not in _DATABASE_METHODS:
        return False
    return any(
        part in _DATABASE_RECEIVERS
        or part.endswith(("_conn", "_connection", "_cursor", "_db", "_repo", "_session"))
        for part in parts[:-1]
    )


def _is_sync_work_call(call_name: str) -> bool:
    terminal = call_name.rsplit(".", 1)[-1]
    return terminal.startswith(_SYNC_WORK_PREFIXES) or terminal.endswith("_sync")


def _normalized_identifier(value: str) -> str:
    return value.strip("_").lower()
