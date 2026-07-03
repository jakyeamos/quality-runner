# Quality Runner Agent Handoff

- Schema: quality-runner-agent-handoff-v0.2
- Status: gates-blocked
- Implementation allowed: false

## Gate Verification

- Status: blocked
- Recommended classification: environment-or-dependency-blocker
- Primary blocker class: dependency-setup

### Gate Blocker Groups

- dependency-setup: lint, tests

### Gate Blockers

- lint: failed (dependency-setup-blocker).
  - Setup: `pnpm install`
  - Action: Run dependency setup before rerunning QR.
- tests: skipped (dependency-setup-blocked); blocked by lint.

## Next Slice

- ID: resolve-gate-verification-blockers
- Title: Resolve dependency setup gate blockers
- Priority: high

### Action Groups

- dependency-setup: lint, tests
  - Run dependency setup once, then rerun the blocked gates.

## Verification Gates

- Rerun `quality-runner refresh . --run-id-prefix <next-run> --handoff-output /tmp/qr-handoff.md --json`.

