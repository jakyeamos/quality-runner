# Contributing

Quality Runner is an audit-and-plan tool. Contributions must preserve the v1
safety boundary: the tool may write `.quality-runner/runs/<run-id>/` artifacts,
but it must not edit source files, install dependencies, create commits, call
remote services, or execute remediation.

## Development

Run the full local quality ladder before opening a pull request:

```bash
python3.14 -m pytest -q
ruff check .
ruff format --check .
basedpyright
vulture . --min-confidence 70
uv run --with pytest pytest -q
python3.14 scripts/run_pytest_with_lcov.py
pre-cr run --workspace . --json
```

Pre-CR is changed-line readiness. It is expected to block with `no-changes` on an
unchanged workspace; use it after editing or staging files, and use the LCOV
script above for full-suite coverage generation.

## Tests

Feature work should include behavior-focused tests. Prefer tests that exercise
the public CLI, MCP tool surface, workflow functions, or artifact contracts.

## Release Checks

Before tagging a release, verify:

- package build succeeds with `uv build`
- installed `quality-runner` and `quality-runner-mcp` console scripts run
- artifact schemas and README examples match the implementation
- no generated `uv.lock`, `.quality-runner/`, `.venv/`, or cache files are staged
