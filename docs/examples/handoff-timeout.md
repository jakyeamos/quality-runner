# Quality Runner Agent Handoff

- Schema: quality-runner-agent-handoff-v0.2
- Status: gates-blocked
- Implementation allowed: false

## Gate Verification

- Status: blocked
- Recommended classification: workflow-timeout-blocker
- Primary blocker class: workflow-timeout
- Failure type: workflow-timeout

### Gate Blocker Groups

- workflow-timeout: workflow-timeout

### Gate Blockers

- workflow-timeout: failed (workflow-timeout).
  - Action: Add `data/cache/**` to scan_exclusions only if it is generated/cache data rather than source-owned code, rerun refresh, and keep the 300s total timeout only if the pruned run still needs more evidence
  - Last traversal directory: `data/cache`
  - Scan progress: 5000 visited paths, 120 skipped paths
  - Suggested scan exclusion: `data/cache/**` (timeout ended inside a data/cache-like path after 5000 visited paths)

## Next Slice

- ID: resolve-gate-verification-blockers
- Title: Resolve workflow timeout blockers
- Priority: high

### Action Groups

- workflow-timeout: workflow-timeout
  - Add `data/cache/**` to scan_exclusions only if it is generated/cache data rather than source-owned code, rerun refresh, and keep the 300s total timeout only if the pruned run still needs more evidence.

## Verification Gates

- Rerun `quality-runner refresh . --run-id-prefix <next-run> --handoff-output /tmp/qr-handoff.md --json`.

