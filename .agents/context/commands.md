# Commands and quality gates

last_reviewed: 2026-08-11

Use `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`,
and `uv run basedpyright` for source verification. For fleet changes, run the
scoped audit first, then replay, publish the feed, and read it back through
Pronto. `--changed-only` constrains dynamic execution only; it does not reduce
static fleet assessment. Fleet dynamic execution prefers root aggregate gates,
fails closed on unbounded package-only surfaces, honors repository gate
timeouts only within the CLI ceiling, and never runs discovered mutating or
unknown-risk formatters.

For release preparation, build both archives and run
`uv run --locked quality-runner release-boundary . --dist-dir dist --json`.
Every applicable change-matrix surface must be classified as `public_core`,
`public_adapter`, or `local_only`; public adapters require sanitized contract
fixtures, and local operator wiring must not ship. The command persists
`.quality-runner/release-boundary.json` using schema v2. Release consumers must
require its exact branch and commit, matching matrix and artifact digests, and
all checks passed; v1, stale, dirty, or missing evidence is not releasable.

The Mac Control fleet lane accepts `mac-control-task-manifest/v4` as the only
scoring implementation format. Quality Runner derives the eight semantic
results by resolving typed task claims to repository-relative source anchors
and tokens. V1 through v3 remain readable declaration-only formats, retain
their declared count for explanation, and score `0/8`. Validate the lane with
`uv run pytest -q tests/test_mac_control.py`, then replay and publish the
companion feed before Pronto readback.
