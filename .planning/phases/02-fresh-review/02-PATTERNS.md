# Phase 2: Fresh Review - Pattern Map

## File Classification

| Planned role | Closest analog | Pattern to preserve |
|--------------|----------------|---------------------|
| Review CLI parser | `quality_runner/cli.py` | Add a subparser, keep parser construction separate from payload dispatch, and preserve `--json` behavior. |
| Review CLI payload | `quality_runner/cli_payload.py` | Validate repo paths, call a domain payload function, and return JSON-safe dictionaries. |
| Review artifact writing | `quality_runner/artifacts.py` | Use `prepare_artifact_dir`, `write_json`, and `write_text`; preserve run-id and symlink safety. |
| Review JSON schemas | `quality_runner/schemas/resolution-ledger.schema.json` | Draft 2020-12 schema, stable `$id`, const schema name, required fields, and explicit enum values. |
| Review state | `quality_runner/code_quality_ledger.py` | Use stable fingerprints, sorted entries, explicit statuses, and local run history. |
| Review Markdown | `quality_runner/handoff_markdown.py` | Render sections from the canonical machine payload; avoid a second source of truth. |
| Review MCP tool | `quality_runner/mcp.py` | Add `list_tools` schema, validate arguments, call a payload, and return structured MCP results. |
| Review tests | `tests/test_artifacts.py`, `tests/test_mcp.py`, `tests/test_cli.py` | Use `tmp_path`, subprocess CLI checks where needed, and explicit path/output assertions. |

## Shared Patterns

- **Read-only boundary:** `README.md` and `SECURITY.md` define that Quality
  Runner writes only `.quality-runner` artifacts and does not edit source,
  install dependencies, commit, call remote services, or execute remediation.
- **Path safety:** `artifact_dir` rejects absolute, separator-containing, dot, and
  parent-traversal run ids; artifact writers reject symlinked parents and leaves.
- **Canonical payload:** JSON is the source of truth; Markdown is derived from
  the same normalized object.
- **Stable state:** resolution entries use a fingerprint plus status, severity,
  location, confidence, reason, owner, and expiry fields.
- **MCP schema discipline:** tool schemas use `additionalProperties: false`,
  explicit required fields, and JSON-RPC errors for invalid parameters.

## No Analog Found

- Mode-specific fresh context packet construction.
- BYO-agent/file adapter result validation.
- Review-specific report/fix-prompt schemas.
- Active-loop cycle isolation and end-of-cycle matching.

These new surfaces should follow the shared patterns above and the architecture
defined in `02-RESEARCH.md` rather than introducing a dependency or parallel
artifact root.
