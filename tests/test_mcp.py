from __future__ import annotations

import json
from pathlib import Path

from quality_runner import __version__
from quality_runner.mcp import call_tool, handle_jsonrpc_message, list_tools, main
from test_support.quality_runner_fixtures import write_js_fixture


def test_mcp_lists_quality_runner_tools() -> None:
    tool_names = {tool["name"] for tool in list_tools()}

    assert tool_names == {
        "quality_runner_doctor",
        "quality_runner_inspect_repo",
        "quality_runner_run",
        "quality_runner_status",
        "quality_runner_export_handoff",
    }


def test_mcp_doctor_reports_ready_without_implementation_permission() -> None:
    result = call_tool("quality_runner_doctor", {})

    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["schema"] == "quality-runner-doctor-result-v0.1"
    assert structured["status"] == "ready"
    assert structured["implementation_allowed"] is False


def test_mcp_run_returns_structured_content(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    result = call_tool(
        "quality_runner_run",
        {"repo_root": str(tmp_path), "run_id": "mcp-run"},
    )

    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["schema"] == "quality-runner-run-result-v0.1"
    assert structured["implementation_allowed"] is False
    assert Path(structured["artifact_paths"]["agent_handoff_md"]).exists()
    standards = json.loads(Path(structured["artifact_paths"]["standards_json"]).read_text())
    assert standards["profile"] == "default"


def test_mcp_run_accepts_ci_status_json(tmp_path: Path) -> None:
    ci_status = tmp_path / "ci-status.json"
    ci_status.write_text(json.dumps({"checks": [{"name": "Lint", "status": "completed"}]}))

    result = call_tool(
        "quality_runner_run",
        {
            "repo_root": str(tmp_path),
            "run_id": "mcp-ci-run",
            "standards": "default",
            "ci_status_json": str(ci_status),
        },
    )

    repo_scan = json.loads(
        Path(result["structuredContent"]["artifact_paths"]["repo_scan_json"]).read_text()
    )
    assert repo_scan["ci_checks"][0]["name"] == "Lint"


def test_mcp_default_run_ids_do_not_collide_for_quick_calls(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    results = [
        call_tool("quality_runner_inspect_repo", {"repo_root": str(tmp_path)}),
        call_tool("quality_runner_inspect_repo", {"repo_root": str(tmp_path)}),
        call_tool("quality_runner_run", {"repo_root": str(tmp_path)}),
        call_tool("quality_runner_run", {"repo_root": str(tmp_path)}),
    ]

    run_ids = [result["structuredContent"]["run_id"] for result in results]
    assert len(set(run_ids)) == len(run_ids)
    assert sorted(
        path.name for path in (tmp_path / ".quality-runner" / "runs").iterdir()
    ) == sorted(run_ids)


def test_mcp_jsonrpc_tools_call(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    response = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "quality_runner_inspect_repo",
                "arguments": {
                    "repo_root": str(tmp_path),
                    "run_id": "mcp-inspect",
                    "standards": "default",
                },
            },
        }
    )

    assert response is not None
    assert response["id"] == 1
    assert response["result"]["structuredContent"]["schema"] == (
        "quality-runner-inspect-result-v0.1"
    )


def test_mcp_initialize_and_tools_list_jsonrpc() -> None:
    initialize = handle_jsonrpc_message({"jsonrpc": "2.0", "id": "init", "method": "initialize"})
    tools = handle_jsonrpc_message({"jsonrpc": "2.0", "id": "tools", "method": "tools/list"})

    assert initialize is not None
    assert initialize["result"]["serverInfo"] == {"name": "quality-runner", "version": __version__}
    assert initialize["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert tools is not None
    assert len(tools["result"]["tools"]) == 5


def test_mcp_notifications_do_not_return_response() -> None:
    response = handle_jsonrpc_message({"jsonrpc": "2.0", "method": "notifications/initialized"})

    assert response is None


def test_mcp_returns_error_for_unknown_method_and_tool() -> None:
    unknown_method = handle_jsonrpc_message(
        {"jsonrpc": "2.0", "id": 10, "method": "quality_runner/unknown"}
    )
    unknown_tool = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "quality_runner_missing", "arguments": {}},
        }
    )

    assert unknown_method is not None
    assert unknown_method["error"]["code"] == -32601
    assert "Unsupported JSON-RPC method" in unknown_method["error"]["message"]
    assert unknown_tool is not None
    assert unknown_tool["error"]["code"] == -32602
    assert "Unknown Quality Runner MCP tool" in unknown_tool["error"]["message"]


def test_mcp_returns_error_for_invalid_message_shape() -> None:
    response = handle_jsonrpc_message(["not", "a", "message"])

    assert response is not None
    assert response["id"] is None
    assert response["error"]["code"] == -32600
    assert "JSON-RPC message must be an object" in response["error"]["message"]


def test_mcp_status_lists_existing_runs(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    call_tool("quality_runner_run", {"repo_root": str(tmp_path), "run_id": "mcp-run-a"})
    call_tool("quality_runner_inspect_repo", {"repo_root": str(tmp_path), "run_id": "mcp-run-b"})

    result = call_tool("quality_runner_status", {"repo_root": str(tmp_path)})

    assert result["isError"] is False
    assert result["structuredContent"] == {
        "schema": "quality-runner-status-result-v0.1",
        "repo_root": str(tmp_path.resolve()),
        "runs": ["mcp-run-a", "mcp-run-b"],
        "implementation_allowed": False,
    }


def test_mcp_status_excludes_symlinked_run_directories(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    call_tool("quality_runner_run", {"repo_root": str(tmp_path), "run_id": "real-run"})
    external_run = tmp_path.parent / f"{tmp_path.name}-external-run"
    external_run.mkdir()
    runs_dir = tmp_path / ".quality-runner" / "runs"
    (runs_dir / "linked-run").symlink_to(external_run, target_is_directory=True)

    result = call_tool("quality_runner_status", {"repo_root": str(tmp_path)})

    assert result["isError"] is False
    assert result["structuredContent"]["runs"] == ["real-run"]


def test_mcp_export_handoff_returns_existing_handoff(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    call_tool("quality_runner_run", {"repo_root": str(tmp_path), "run_id": "handoff-run"})

    result = call_tool(
        "quality_runner_export_handoff",
        {"repo_root": str(tmp_path), "run_id": "handoff-run"},
    )

    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["schema"] == "quality-runner-export-handoff-result-v0.1"
    assert structured["run_id"] == "handoff-run"
    assert structured["handoff_path"].endswith("agent-handoff.md")
    assert "# Quality Runner Agent Handoff" in structured["handoff"]


def test_mcp_export_handoff_rejects_unsafe_run_id(tmp_path: Path) -> None:
    response = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {
                "name": "quality_runner_export_handoff",
                "arguments": {"repo_root": str(tmp_path), "run_id": "../escape"},
            },
        }
    )

    assert response is not None
    assert response["error"]["code"] == -32602
    assert response["error"]["message"] == "run_id must be a non-empty single path segment"


def test_mcp_export_handoff_rejects_symlinked_handoff_leaf_without_leaking_contents(
    tmp_path: Path,
) -> None:
    external_handoff = tmp_path.parent / f"{tmp_path.name}-external-handoff.md"
    external_handoff.write_text("external secret handoff\n", encoding="utf-8")
    run_dir = tmp_path / ".quality-runner" / "runs" / "linked-leaf"
    run_dir.mkdir(parents=True)
    (run_dir / "agent-handoff.md").symlink_to(external_handoff)

    response = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "quality_runner_export_handoff",
                "arguments": {"repo_root": str(tmp_path), "run_id": "linked-leaf"},
            },
        }
    )

    assert response is not None
    assert response["error"]["code"] == -32602
    assert response["error"]["message"] == "artifact file must not be a symlink"
    assert "external secret handoff" not in json.dumps(response)


def test_mcp_export_handoff_rejects_symlinked_artifact_directories(tmp_path: Path) -> None:
    cases = [
        (".quality-runner",),
        (".quality-runner", "runs"),
        (".quality-runner", "runs", "linked-run"),
    ]

    for index, symlink_parts in enumerate(cases):
        repo = tmp_path / f"repo-{index}"
        repo.mkdir()
        external = tmp_path / f"external-{index}"
        external.mkdir()
        if symlink_parts == (".quality-runner",):
            (repo / ".quality-runner").symlink_to(external, target_is_directory=True)
        elif symlink_parts == (".quality-runner", "runs"):
            (repo / ".quality-runner").mkdir()
            (repo / ".quality-runner" / "runs").symlink_to(external, target_is_directory=True)
        else:
            runs_dir = repo / ".quality-runner" / "runs"
            runs_dir.mkdir(parents=True)
            (runs_dir / "linked-run").symlink_to(external, target_is_directory=True)

        response = handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 22 + index,
                "method": "tools/call",
                "params": {
                    "name": "quality_runner_export_handoff",
                    "arguments": {"repo_root": str(repo), "run_id": "linked-run"},
                },
            }
        )

        assert response is not None
        assert response["error"]["code"] == -32602
        assert response["error"]["message"] == "artifact path component must not be a symlink"


def test_mcp_main_preserves_version_behavior(capsys) -> None:
    exit_code = main(["--version"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_mcp_main_stdio_loop_writes_jsonrpc_response(monkeypatch, capsys) -> None:
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    monkeypatch.setattr("sys.stdin", iter([request + "\n"]))

    exit_code = main([])

    assert exit_code == 0
    response = json.loads(capsys.readouterr().out)
    assert response["id"] == 1
    assert len(response["result"]["tools"]) == 5
