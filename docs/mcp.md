# MCP Integration

Run the stdio MCP server:

```bash
quality-runner-mcp
```

The server accepts line-delimited JSON-RPC messages on stdin and writes JSON-RPC
responses to stdout.

The optional `standards` argument selects a standards profile. It defaults to
`default`.

## Tools

Primary `quality-runner-mcp` tools:

### `quality_runner_doctor`

Checks readiness.

```json
{}
```

### `quality_runner_inspect_repo`

Runs the inspect-only workflow.

```json
{
  "repo_root": "/path/to/repo",
  "run_id": "inspect-001",
  "ci_status_json": "/path/to/repo/ci-status.json"
}
```

### `quality_runner_run`

Runs the full audit-and-plan workflow.

```json
{
  "repo_root": "/path/to/repo",
  "run_id": "baseline-001",
  "ci_status_json": "/path/to/repo/ci-status.json"
}
```

### `quality_runner_status`

Lists non-symlink run directories under `.quality-runner/runs`.

```json
{
  "repo_root": "/path/to/repo"
}
```

### `quality_runner_export_handoff`

Returns an existing `agent-handoff.md` for a run.

```json
{
  "repo_root": "/path/to/repo",
  "run_id": "baseline-001"
}
```

The export path rejects unsafe run ids and symlinked artifact components before
reading.

## JSON-RPC Example

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"quality_runner_run","arguments":{"repo_root":"/path/to/repo","run_id":"baseline-001"}}}
```

All successful tool calls return:

- `isError`
- `content`
- `structuredContent`

## Repo Quality Certifier Compatibility

Quality Runner also installs `repo-quality-certifier-mcp` for existing
Repo Quality Certifier integrations. It exposes:

- `repo_quality_certifier_plan`
- `repo_quality_certifier_doc_quality`

Use these tools only for compatibility with callers that still expect the old
certifier schema names. New integrations should prefer `quality_runner_run`,
`quality_runner_status`, and `quality_runner_export_handoff`.
