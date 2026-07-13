# MCP Integration

Run the stdio server with `quality-runner-mcp`. It accepts line-delimited
JSON-RPC on stdin and writes one JSON-RPC response per request on stdout.

## Preferred outcome tools

New integrations should use the additive journey tools:

- `quality_runner_audit_outcome` prepares audit evidence and a remediation plan;
  it can use `mode: "inspect"` for discovery-only evidence.
- `quality_runner_review_outcome` makes a packet-only review visibly
  `awaiting-evidence` rather than treating it as a clean review.
- `quality_runner_verify_outcome` defaults to evidence-only verification. It
  only executes commands when `execute_gates` and `worktree_mode: "disposable"`
  are both explicit; a disposable checkout is not a host sandbox.
- `quality_runner_runs_outcome` reads bounded run history without writing a new
  summary artifact.

Each tool returns the existing `quality-runner-mcp-result-v0.1` wrapper. Its
`structuredContent` is the new `quality-runner-outcome-v0.2` contract, which
leads with state, confidence, writes, safety, and a next action. The precise
argument schemas are advertised through `tools/list` and owned by
`quality_runner.mcp_journeys`; clients should discover them rather than copying
a static option table.

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"quality_runner_audit_outcome","arguments":{"repo_root":"/path/to/repo","run_id":"baseline-001"}}}
```

The outcome tools validate their advertised fields strictly. `intent_file`, when
used by audit or verify, must remain inside the target repository. New tools use
`profile`; legacy inspect/run tools continue to use `standards` so their v1
contract is unchanged.

## Legacy compatibility

The established MCP tools remain callable and retain their v1
`structuredContent` shapes. Use `tools/list` for their current names and input
schemas; do not assume that a legacy CLI projection and a legacy MCP projection
have identical fields.

`quality_runner_review` remains the v1 review tool even though the CLI `review`
journey is outcome-first by default. Prefer `quality_runner_review_outcome`
when a caller needs the cross-journey outcome contract. The direct-replacement
legacy tools identify their support window in `tools/list`; their v1 payloads
do not gain new fields during the transition. The [Upgrade and Compatibility
Guide](upgrade.md) is the canonical policy and rollback reference.

Existing Repo Quality Certifier callers can continue to use
`repo-quality-certifier-mcp` and its published compatibility tools. Those
compatibility islands do not currently have a retirement schedule.

Fresh Review has the same two-phase contract over MCP as it does on the CLI:
the first call creates a packet-ready run, and a later call supplies a response
inside that run. The response must bind to the saved packet's run id, mode, and
hash; a response that cannot prove that binding is returned as incomplete review
evidence. Binding validates the declared packet, not reviewer identity or file
access outside the packet boundary. Outcome-tool `writes.artifact_paths` lists
the lifecycle files actually created; legacy review payloads retain their v1
six-path surface. See the [CLI reference](cli.md#quality-runner-review) for the
safety and fixer-handoff rules.

## JSON-RPC behavior

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

Successful tool calls expose `isError`, human-readable `content`, and
machine-readable `structuredContent`. Invalid request shapes are reported as
JSON-RPC invalid-parameter errors; ordinary outcome states such as blocked
verification remain successful tool calls so automation can follow the supplied
next action.
