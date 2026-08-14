# Commands and quality gates

last_reviewed: 2026-08-13

Use `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`,
and `uv run basedpyright` for source verification. For fleet changes, run the
scoped audit first, then replay, publish the feed, and read it back through
Pronto. `--changed-only` constrains dynamic execution only; it does not reduce
static fleet assessment. To audit one standard across the entire bounded
inventory, use a static-only standard scope:

```sh
uv run --locked qr fleet audit run --all \
  --projects-root /path/to/projects \
  --standard matrix-maintenance --json
```

The result writes a private `standard-report.json` that lists every audited
repository and its honest state. A standard-scoped snapshot is intentionally
not publishable as the canonical all-standards maturity feed; replay it and
inspect the report directly. Fleet dynamic execution prefers root aggregate gates,
fails closed on unbounded package-only surfaces, honors repository gate
timeouts only within the CLI ceiling, and never runs discovered mutating or
unknown-risk formatters.

`matrix_maintenance` is also a canonical dimension of the complete fleet audit.
It contributes to each applicable repository's `dimension_scores`,
`maturity_score`, `dimension_gaps`, fleet means, and Pronto maturity
remediation. The scoped command above is a diagnostic slice; after it identifies
gaps, rerun the complete audit without `--standard`, pass replay, publish that
feed, and refresh Pronto before claiming the score or remediation queue reflects
the latest evidence.

The published feed is `quality-runner-maturity-feed/v2`. Its repository score
flows from dimensions to explicit capabilities to seven weighted pillars, not
from the count of flat findings. Use `repository_maturity.pillars` and their
`capabilities` for the quality vector and
`repository_maturity.evidence` for measurement coverage, freshness, conditional
applicability, and unmapped dimensions. Conditional capabilities preserve
`applicable`, `not_applicable`, or `unknown` state. `source_dimension_mean`
is retained only for migration diagnostics. Only a finding with
`confirmed_critical_risk: true` in correctness, security, or operability
applies the score cap; blocker/P0 state alone remains a quality-outcome signal.
Agent growth health is diagnostic and does not add a fifth score beside the
four consolidated human/agent capabilities.

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
