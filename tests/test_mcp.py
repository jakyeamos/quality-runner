from __future__ import annotations

import json
from pathlib import Path

from quality_runner import __version__
from quality_runner.mcp import call_tool, handle_jsonrpc_message, list_tools, main
from test_support.quality_runner_fixtures import write_js_fixture


def test_mcp_lists_quality_runner_tools() -> None:
    tools = list_tools()
    tool_names = {tool["name"] for tool in tools}

    assert tool_names == {
        "quality_runner_doctor",
        "quality_runner_inspect_repo",
        "quality_runner_run",
        "quality_runner_status",
        "quality_runner_export_handoff",
        "quality_runner_gate",
        "quality_runner_gate_status",
        "quality_runner_gate_respond",
        "quality_runner_propose_fix",
        "quality_runner_review",
        "quality_runner_audit_outcome",
        "quality_runner_review_outcome",
        "quality_runner_verify_outcome",
        "quality_runner_runs_outcome",
    }
    descriptions = {tool["name"]: tool["description"] for tool in tools}
    assert "supported through 0.7.x" in descriptions["quality_runner_review"]
    assert "quality_runner_audit_outcome" in descriptions["quality_runner_inspect_repo"]
    assert "quality_runner_audit_outcome" in descriptions["quality_runner_run"]


def test_mcp_doctor_reports_ready_without_implementation_permission() -> None:
    result = call_tool("quality_runner_doctor", {})

    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["schema"] == "quality-runner-doctor-result-v0.1"
    assert structured["status"] == "ready"
    assert structured["implementation_allowed"] is False


def test_mcp_review_blind_mode_is_packet_only(tmp_path: Path) -> None:
    result = call_tool(
        "quality_runner_review",
        {"repo_root": str(tmp_path), "mode": "blind", "run_id": "mcp-review"},
    )
    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["status"] == "review-not-run"
    assert structured["outcome"] == "packet-ready"
    assert structured["summary"].startswith("Review packet ready:")
    assert "next_action" in structured
    assert structured["breadth"] == "related"
    assert set(structured["artifact_paths"]) == {
        "review_manifest_json",
        "review_context_json",
        "review_report_json",
        "review_report_md",
        "review_agent_packet_md",
        "review_fix_prompts_md",
    }


def test_mcp_audit_outcome_returns_additive_v2_projection(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    result = call_tool(
        "quality_runner_audit_outcome",
        {"repo_root": str(tmp_path), "run_id": "mcp-outcome-audit"},
    )

    assert result["schema"] == "quality-runner-mcp-result-v0.1"
    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["schema"] == "quality-runner-outcome-v0.2"
    assert structured["journey"] == "audit"
    assert structured["state"] == "action-required"
    assert structured["source"] == {
        "legacy_schema": "quality-runner-run-result-v0.1",
        "legacy_status": "planned",
    }


def test_mcp_review_outcome_keeps_packet_ready_truthful(tmp_path: Path) -> None:
    result = call_tool(
        "quality_runner_review_outcome",
        {"repo_root": str(tmp_path), "mode": "blind", "run_id": "mcp-outcome-review"},
    )

    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["schema"] == "quality-runner-outcome-v0.2"
    assert structured["journey"] == "review"
    assert structured["state"] == "awaiting-evidence"
    assert structured["assessment"] == "packet-ready"
    assert structured["confidence"]["level"] == "none"
    assert structured["source"]["legacy_schema"] == "quality-runner-review-result-v0.1"
    paths = structured["writes"]["artifact_paths"]
    assert "review_adapter_response_template_json" in paths
    assert "review_execution_json" in paths
    assert "review_adapter_response_json" not in paths
    assert all(Path(path).exists() for path in paths.values())


def test_mcp_verify_outcome_defaults_to_evidence_only(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)

    result = call_tool(
        "quality_runner_verify_outcome",
        {"repo_root": str(tmp_path), "run_id": "mcp-outcome-verify"},
    )

    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["schema"] == "quality-runner-outcome-v0.2"
    assert structured["journey"] == "verify"
    assert structured["state"] == "blocked"
    assert structured["safety"]["mode"] == "evidence-only"
    assert structured["next_action"] == {
        "kind": "authorize-verification",
        "summary": "Authorize disposable execution to replace evidence-only gate records.",
        "command": f"quality-runner verify {tmp_path} --run-id mcp-outcome-verify "
        "--execute-gates --worktree-mode disposable",
        "requires_authorization": True,
    }


def test_mcp_runs_outcome_reads_history_without_persisting_summaries(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    audit = call_tool(
        "quality_runner_audit_outcome",
        {"repo_root": str(tmp_path), "run_id": "mcp-outcome-history"},
    )
    assert audit["isError"] is False

    result = call_tool("quality_runner_runs_outcome", {"repo_root": str(tmp_path)})

    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["schema"] == "quality-runner-outcome-v0.2"
    assert structured["journey"] == "runs"
    assert structured["state"] == "complete"
    assert structured["assessment"] == "history"
    assert structured["writes"]["state"] == "none"
    assert not (
        tmp_path / ".quality-runner" / "runs" / "mcp-outcome-history" / "run-summary.json"
    ).exists()


def test_mcp_runs_outcome_rejects_an_unsafe_selected_run_id(tmp_path: Path) -> None:
    response = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "quality_runner_runs_outcome",
                "arguments": {"repo_root": str(tmp_path), "run_id": "../escape"},
            },
        }
    )

    assert response is not None
    assert response["error"]["code"] == -32602


def test_mcp_review_missing_task_is_invalid_params(tmp_path: Path) -> None:
    response = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "quality_runner_review", "arguments": {"repo_root": str(tmp_path)}},
        }
    )
    assert response is not None
    assert response["error"]["code"] == -32602


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
    assert len(tools["result"]["tools"]) == 14


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


def test_mcp_gate_creates_driveable_run(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    call_tool("quality_runner_run", {"repo_root": str(tmp_path), "run_id": "gate-source"})

    result = call_tool(
        "quality_runner_gate",
        {
            "repo_root": str(tmp_path),
            "run_id": "gate-source",
            "gate_run_id": "mcp-gate-001",
            "intent": "Exercise gate controller over MCP",
        },
    )

    structured = result["structuredContent"]
    assert structured["schema"] == "quality-runner-gate-run-result-v0.1"
    assert structured["gate_run"]["gate_run_id"] == "mcp-gate-001"
    assert structured["implementation_allowed"] is False


def test_mcp_propose_fix_writes_proposal_artifact(tmp_path: Path) -> None:
    from test_support.quality_runner_fixtures import write_complete_js_fixture

    write_complete_js_fixture(tmp_path)
    source = tmp_path / "src" / "app" / "page.tsx"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("const value: any = 1;\n", encoding="utf-8")
    call_tool("quality_runner_run", {"repo_root": str(tmp_path), "run_id": "mcp-propose-run"})
    handoff = json.loads(
        (tmp_path / ".quality-runner/runs/mcp-propose-run/agent-handoff.json").read_text()
    )

    result = call_tool(
        "quality_runner_propose_fix",
        {
            "repo_root": str(tmp_path),
            "run_id": "mcp-propose-run",
            "finding_group": handoff["next_slice"]["id"],
        },
    )

    structured = result["structuredContent"]
    assert structured["schema"] == "quality-runner-fix-propose-result-v0.1"
    assert structured["implementation_allowed"] is False
    assert structured["fix_proposals"]["applied"] is False


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
    assert len(response["result"]["tools"]) == 14
