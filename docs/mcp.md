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
  "ci_status_json": "/path/to/repo/ci-status.json",
  "intent": "Ship the auth refactor without widening the public API",
  "intent_file": "/path/to/repo/.quality-runner/intent.json"
}
```

`intent` and `intent_file` are optional and mutually usable: when both are
omitted, no intent artifact is written. `intent_file` must live inside the
target repository.

`intent` and `intent_file` are optional and mutually usable: when both are
omitted, no intent artifact is written. `intent_file` must live inside the
target repository.

### `quality_runner_gate`

Creates a driveable gate run from an existing Quality Runner run.

```json
{
  "repo_root": "/path/to/repo",
  "run_id": "refresh-001-verify",
  "gate_run_id": "gate-20260707-001",
  "intent": "Land Phase 2 gate controller with JSON-only responses"
}
```

### `quality_runner_gate_status`

Reads an in-flight gate run and append-only response history.

```json
{
  "repo_root": "/path/to/repo",
  "gate_run_id": "gate-20260707-001"
}
```

### `quality_runner_gate_respond`

Records a controller decision without executing fixes.

```json
{
  "repo_root": "/path/to/repo",
  "gate_run_id": "gate-20260707-001",
  "action": "route-next-slice",
  "finding_ids": ["gate-pnpm-install"],
  "notes": "Worker should run pnpm install before re-verify."
}
```

### `quality_runner_propose_fix`

Writes structured fix proposals for a remediation finding group.

```json
{
  "repo_root": "/path/to/repo",
  "run_id": "refresh-001-verify",
  "finding_group": "remediate-structural-src-app-page-tsx"
}
```

### `quality_runner_run`

Runs the full audit-and-plan workflow.

```json
{
  "repo_root": "/path/to/repo",
  "run_id": "baseline-001",
  "ci_status_json": "/path/to/repo/ci-status.json",
  "intent": "Land Phase 1 schema semantics with additive artifacts only"
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
`quality_runner_gate`, `quality_runner_gate_status`, `quality_runner_gate_respond`,
`quality_runner_propose_fix`, `quality_runner_status`, and `quality_runner_export_handoff`.
