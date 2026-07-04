from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from repo_quality_certifier.cli import build_doc_quality_payload, build_plan_payload

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_RESULT_SCHEMA = "repo-quality-certifier-mcp-result-v0.1"


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "repo_quality_certifier_plan",
            "description": "Generate repo quality certification scan, matrix, rubric, and rollout artifacts.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_root": {"type": "string"},
                    "run_id": {"type": "string"},
                    "output_dir": {"type": "string"},
                },
                "required": ["repo_root"],
            },
        },
        {
            "name": "repo_quality_certifier_doc_quality",
            "description": "Generate certification artifacts and validate generated audit/implementation docs.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "repo_root": {"type": "string"},
                    "run_id": {"type": "string"},
                    "output_dir": {"type": "string"},
                },
                "required": ["repo_root"],
            },
        },
    ]


def _string_arg(arguments: dict[str, Any], key: str, default: str | None = None) -> str | None:
    value = arguments.get(key, default)
    return value if isinstance(value, str) and value else default


def _paths(arguments: dict[str, Any]) -> tuple[Path, str, Path | None]:
    repo_root = _string_arg(arguments, "repo_root")
    if repo_root is None:
        raise ValueError("repo_root is required")
    run_id = _string_arg(arguments, "run_id", "repo-quality-certifier-mcp-run")
    output_dir = _string_arg(arguments, "output_dir")
    return Path(repo_root), str(run_id), Path(output_dir) if output_dir else None


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, indent=2, sort_keys=True)
    return {
        "schema": MCP_RESULT_SCHEMA,
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": False,
    }


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    repo_root, run_id, output_dir = _paths(args)
    if name == "repo_quality_certifier_plan":
        return _tool_result(
            build_plan_payload(repo_root=repo_root, run_id=run_id, output_dir=output_dir)
        )
    if name == "repo_quality_certifier_doc_quality":
        return _tool_result(
            build_doc_quality_payload(repo_root=repo_root, run_id=run_id, output_dir=output_dir)
        )
    raise ValueError(f"Unknown repo quality certifier MCP tool: {name}")


def handle_jsonrpc_message(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "notifications/initialized":
        return None
    try:
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "repo-quality-certifier",
                    "version": "0.1.0",
                },
            }
        elif method == "tools/list":
            result = {"tools": list_tools()}
        elif method == "tools/call":
            params = message.get("params")
            params = params if isinstance(params, dict) else {}
            tool_name = params.get("name")
            if not isinstance(tool_name, str):
                raise ValueError("tools/call requires params.name")
            arguments = params.get("arguments")
            result = call_tool(tool_name, arguments if isinstance(arguments, dict) else {})
        else:
            raise ValueError(f"Unsupported JSON-RPC method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": str(exc),
            },
        }


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle_jsonrpc_message(json.loads(line))
        if response is None:
            continue
        print(json.dumps(response, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
