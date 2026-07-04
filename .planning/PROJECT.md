# quality-runner

## What This Is

quality-runner is an existing local codebase in Jakye's QR remediation fleet. This GSD project was initialized from Quality Runner documentation so remediation can be planned, executed, verified, committed, and pushed in atomic repo-local phases.

## Core Value

Keep quality-runner healthy by resolving Quality Runner findings with behavior-preserving, evidence-backed remediation.

## Requirements

### Validated

- Existing repository behavior is the baseline unless a QR hardening finding requires safer input handling.

### Active

- [ ] Resolve QR findings from run qr-fleet-continue-20260704-quality-runner using cluster-oriented remediation.
- [ ] Verify remediation with focused repo checks and post-remediation QR comparison.
- [ ] Keep QR advisory-only; source changes happen through GSD execution and git commits.

### Out of Scope

- Broad rewrites outside the QR clusters.
- Pulling QR into execution/mutation responsibilities.
- Changing product/API/design behavior without an explicit QR hardening need or user decision.

## Context

- Repo path: `/Users/jakyeamos/projects/quality-runner`
- QR summary: `/Users/jakyeamos/.local/state/quality-runner/fleet/per-repo-summaries-20260704/quality-runner.md`
- QR run directory: `/Users/jakyeamos/projects/quality-runner/.quality-runner/runs/qr-fleet-continue-20260704-quality-runner`
- Package or project files detected: `pyproject.toml`

## Constraints

- **Git:** Commit in atomic units scoped to this repo and concern.
- **Verification:** A cluster is complete only with focused checks plus QR comparison evidence.
- **Package management:** Use pnpm for JavaScript package scripts.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Use QR per-repo summaries as PRDs | They contain the current finding clusters, artifacts, and verification suggestions. | Pending execution |
| Keep Quality Runner advisory-only | The user explicitly does not want execution pulled into QR. | Good |

---
*Last updated: 2026-07-04 after QR remediation GSD bootstrap*
