# Common failure modes and recovery

last_reviewed: 2026-07-22

- Dirty, detached, stale, or prunable target worktrees: stop execution and
  capture the state; use a verified disposable copy rather than cleaning the
  user checkout.
- Missing consent or unavailable gates: record `blocked` or `unavailable`; do
  not silently downgrade to a passing result.
- Stale manifests, packets, or evidence: refresh from the current checkout and
  regenerate the dependent artifact with a new provenance hash.
- Dependency or network failures: distinguish local cache/setup failures from
  provider or registry access; retry only after checking the relevant gate.
- Malformed or incompatible artifacts: validate the schema and migration path;
  retain the original artifact and report the transform failure.
- Cache identity mismatch: discard only the scoped cache through the supported
  command and rerun from a current refresh; do not delete broad directories.

Use [docs/troubleshooting.md](../../docs/troubleshooting.md) and
[docs/agent-usage.md](../../docs/agent-usage.md) for the supported recovery
surfaces.
