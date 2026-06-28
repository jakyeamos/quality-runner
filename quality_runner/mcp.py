from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from quality_runner import __version__
from quality_runner.artifacts import artifact_dir
from quality_runner.cli import DOCTOR_RESULT_SCHEMA
from quality_runner.workflow import generated_run_id, inspect_payload, run_payload

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_RESULT_SCHEMA = "quality-runner-mcp-result-v0.1"

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


class JsonRpcError(ValueError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def list_tools() -> list[dict[str, Any]]:
    repo_schema = {
        "type": "object",
        "properties": {
            "repo_root": {"type": "string"},
            "run_id": {"type": "string"},
            "standards": {"type": "string"},
        },
        "required": ["repo_root"],
        "additionalProperties": False,
    }
    handoff_schema = {
        "type": "object",
        "properties": {
            "repo_root": {"type": "string"},
            "run_id": {"type": "string"},
        },
        "required": ["repo_root", "run_id"],
        "additionalProperties": False,
    }
    return [
        {
            "name": "quality_runner_doctor",
            "description": "Check Quality Runner install readiness and version.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "quality_runner_inspect_repo",
            "description": "Inspect repository shape and quality capabilities.",
            "inputSchema": repo_schema,
        },
        {
            "name": "quality_runner_run",
            "description": "Run audit-and-plan workflow and write Quality Runner artifacts.",
            "inputSchema": repo_schema,
        },
        {
            "name": "quality_runner_status",
            "description": "List existing Quality Runner runs for a repository.",
            "inputSchema": {
                "type": "object",
                "properties": {"repo_root": {"type": "string"}},
                "required": ["repo_root"],
                "additionalProperties": False,
            },
        },
        {
            "name": "quality_runner_export_handoff",
            "description": "Return an existing agent handoff for a repository run.",
            "inputSchema": handoff_schema,
        },
    ]


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    args = arguments or {}
    if name == "quality_runner_doctor":
        return _tool_result(_doctor_payload())

    if name == "quality_runner_inspect_repo":
        repo_root = _validated_repo_root(args)
        run_id = _string_arg(args, "run_id") or generated_run_id(suffix="quality-runner-mcp")
        profile = _string_arg(args, "standards") or "jakyeamos"
        return _tool_result(inspect_payload(repo_root=repo_root, run_id=run_id, profile=profile))

    if name == "quality_runner_run":
        repo_root = _validated_repo_root(args)
        run_id = _string_arg(args, "run_id") or generated_run_id(suffix="quality-runner-mcp")
        profile = _string_arg(args, "standards") or "jakyeamos"
        return _tool_result(run_payload(repo_root=repo_root, run_id=run_id, profile=profile))

    if name == "quality_runner_status":
        repo_root = _validated_repo_root(args)
        return _tool_result(_status_payload(repo_root))

    if name == "quality_runner_export_handoff":
        repo_root = _validated_repo_root(args)
        run_id = _required_string_arg(args, "run_id")
        return _tool_result(_export_handoff_payload(repo_root, run_id))

    raise JsonRpcError(JSONRPC_INVALID_PARAMS, f"Unknown Quality Runner MCP tool: {name}")


def handle_jsonrpc_message(message: object) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return _jsonrpc_error(None, JSONRPC_INVALID_REQUEST, "JSON-RPC message must be an object")

    request_id = message.get("id")
    method = message.get("method")
    if method == "notifications/initialized":
        return None
    if not isinstance(method, str):
        return _jsonrpc_error(request_id, JSONRPC_INVALID_REQUEST, "JSON-RPC method is required")

    try:
        if method == "initialize":
            result: dict[str, Any] = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "quality-runner", "version": __version__},
            }
        elif method == "tools/list":
            result = {"tools": list_tools()}
        elif method == "tools/call":
            result = _handle_tools_call(message.get("params"))
        else:
            raise JsonRpcError(
                JSONRPC_METHOD_NOT_FOUND,
                f"Unsupported JSON-RPC method: {method}",
            )
    except JsonRpcError as error:
        return _jsonrpc_error(request_id, error.code, str(error))
    except (OSError, ValueError) as error:
        return _jsonrpc_error(request_id, JSONRPC_INVALID_PARAMS, str(error))
    except Exception as error:
        return _jsonrpc_error(request_id, JSONRPC_INTERNAL_ERROR, str(error))

    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="quality-runner-mcp")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    try:
        parsed = parser.parse_args(args)
    except SystemExit as error:
        code = error.code
        return code if isinstance(code, int) else 2
    if parsed.version:
        print(__version__)
        return 0

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as error:
            response = _jsonrpc_error(None, JSONRPC_PARSE_ERROR, f"Parse error: {error.msg}")
        else:
            response = handle_jsonrpc_message(message)
        if response is None:
            continue
        print(json.dumps(response, separators=(",", ":"), sort_keys=True), flush=True)
    return 0


def _handle_tools_call(params: object) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise JsonRpcError(JSONRPC_INVALID_PARAMS, "tools/call requires object params")
    tool_name = params.get("name")
    if not isinstance(tool_name, str) or not tool_name:
        raise JsonRpcError(JSONRPC_INVALID_PARAMS, "tools/call requires params.name")
    arguments = params.get("arguments", {})
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise JsonRpcError(JSONRPC_INVALID_PARAMS, "tools/call params.arguments must be an object")
    return call_tool(tool_name, arguments)


def _doctor_payload() -> dict[str, Any]:
    return {
        "schema": DOCTOR_RESULT_SCHEMA,
        "status": "ready",
        "version": __version__,
        "implementation_allowed": False,
    }


def _status_payload(repo_root: Path) -> dict[str, Any]:
    runs_dir = repo_root / ".quality-runner" / "runs"
    runs = (
        sorted(path.name for path in runs_dir.iterdir() if path.is_dir())
        if runs_dir.exists()
        else []
    )
    return {
        "schema": "quality-runner-status-result-v0.1",
        "repo_root": str(repo_root),
        "runs": runs,
        "implementation_allowed": False,
    }


def _export_handoff_payload(repo_root: Path, run_id: str) -> dict[str, Any]:
    handoff_path = artifact_dir(repo_root, run_id) / "agent-handoff.md"
    if not handoff_path.exists():
        raise FileNotFoundError(f"agent handoff does not exist: {handoff_path}")
    if not handoff_path.is_file():
        raise ValueError(f"agent handoff is not a file: {handoff_path}")
    return {
        "schema": "quality-runner-export-handoff-result-v0.1",
        "repo_root": str(repo_root),
        "run_id": run_id,
        "handoff_path": str(handoff_path),
        "handoff": handoff_path.read_text(encoding="utf-8"),
        "implementation_allowed": False,
    }


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, indent=2, sort_keys=True)
    return {
        "schema": MCP_RESULT_SCHEMA,
        "isError": False,
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
    }


def _jsonrpc_error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _string_arg(arguments: dict[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise JsonRpcError(JSONRPC_INVALID_PARAMS, f"{key} must be a non-empty string")
    return value


def _required_string_arg(arguments: dict[str, Any], key: str) -> str:
    value = _string_arg(arguments, key)
    if value is None:
        raise JsonRpcError(JSONRPC_INVALID_PARAMS, f"{key} is required")
    return value


def _validated_repo_root(arguments: dict[str, Any]) -> Path:
    value = _required_string_arg(arguments, "repo_root")
    repo_root = Path(value).expanduser().resolve()
    if not repo_root.exists():
        raise FileNotFoundError(f"repo root does not exist: {repo_root}")
    if not repo_root.is_dir():
        raise NotADirectoryError(f"repo root is not a directory: {repo_root}")
    return repo_root


if __name__ == "__main__":
    raise SystemExit(main())
