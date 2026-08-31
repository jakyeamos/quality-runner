---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: GPT-5.6 modernization
status: complete
last_updated: "2026-08-28T21:24:15Z"
progress:
  total_phases: 8
  completed_phases: 8
  total_plans: 8
  completed_plans: 8
  percent: 100
maturity_targets:
  - id: basedpyright-strict
    dimension: typechecking
    target_level: 4
    target_max_level: 4
    status: complete
    interim_gate: basedpyright-standard-full-package
    observed_strict_errors: 0
    promotion_requirement: satisfied by zero strict diagnostics with repeatable local and CI evidence
---

# Planning State

## Project Reference

See `.planning/PROJECT.md` for the established product boundary and
`docs/modernization/` for the modernization target and implementation plan.

**Core value:** Give developers and agents trustworthy local evidence before
they authorize repository changes.

**Current focus:** Fold the post-v0.6.0 feature branches into an isolated
`0.7.0` release candidate while preserving ambiguous dirty worktrees.

## Current Position

- Branch: `codex/main-fold-v0-7-0` in the isolated worktree
  `/private/tmp/quality-runner-main-fold-v0-7-0-20260801`
- Baseline: verified `origin/main` at `9f6c677`; eligible feature history is
  merged through `189cbb7`, including the full-audit, environment-legibility,
  governed bug-learning, semantic-invariant, fleet/security, and task-prevention
  lines.
- Release metadata and readiness discovery fixes: `e3f5f5f`; PR #5 merged at
  `c6e92cc`, tag `v0.6.0` and PyPI publication are verified.
- Audit and planning: complete
- M0 — restore trust at the boundary: complete in `f36dcf4`
- M1 — establish typed review contracts: complete in `cb12746`
- M2 — migrate read-only audit workflow: complete in `3f23204`
- M3 — migrate verification workflow: complete in `8705cc1`
- M4 — deliver journey-led CLI and MCP outcomes: complete in `75d8ac4`
- M5 — make Fresh Review operationally honest: complete in `f5c8610`
- M6 — isolate compatibility and retire duplicate foundations: complete in
  `0b5ac2e` and `56c94d4`
- M7 — release hardening: complete in `279cc8a`; `141635e` adds lexical
  source-evidence protection for private fields, malformed syntax, computed
  logs, and tokenless values. `948107f` prepares v0.5.1 metadata and README
  guidance; `c71b130` completes the pre-tag gate with dependency-audit and
  untrusted-baseline Git-argument hardening. PR #2 merged, `v0.5.1` is
  published to PyPI, and the GitHub Release is public.
- Post-release command surface: complete in `9107285`; `qr` is canonical for
  human-facing help, README quickstart, and packaged entrypoints while
  `quality-runner` remains a compatible alias with preserved JSON behavior.

## Active Phase

- **Phase:** release-fold
- **Slug:** quality-runner-0-7-0
- **Status:** In progress
- **Completion gate:** All eligible feature history is folded from verified
  remote `main`, the missing `v0.6.0` GitHub Release baseline is reconciled,
  and the complete `0.7.0` release ladder passes on the isolated candidate.

## Key Decisions

- Use a parallel typed core with adapters, not a clean rewrite.
- Retain public artifact and compatibility contracts through a versioned
  transition.
- Make command execution explicit and isolated by default.
- Improve the CLI/MCP experience before considering a browser or TUI surface.
- Clear hook-inherited Git environment before traced pytest runs so fixture
  repositories cannot alter the active worktree.
- Keep strict core contracts behind v1 packet/options/state projections until
  the published compatibility cutover.
- Keep executable verification disposable-only; outcome presentation must retain
  its evidence and artifact semantics.
- Make v2 outcomes default for primary CLI journeys while retaining v1 as an
  explicit compatibility projection through the published support window.
- Derive outcome safety claims from observed branch and execution evidence, not
  from requested flags or planned behavior.
- Lead new CLI usage with `qr` while retaining `quality-runner` as a visible
  compatibility alias; keep legacy and advanced commands discoverable in root
  help without making them the first-run path.
- Certify BasedPyright for its declared package scope in both standard and
  strict mode. Strict maturity promotion is supported by equivalent local and
  hosted CI evidence. The historical 4,192-diagnostic report was not reproduced
  against the exact-base checkout: the live strict scan began at 1,198
  diagnostics and the isolated burndown reduced it to zero.
- Treat `codex/qr-command-surface` as semantically superseded: its useful short
  `qr` command is already present, while merging its stale six-file tree would
  delete the current implementation. Preserve the ref rather than merging or
  pruning it during this fold.

## Completed Maturity Target

- `basedpyright-strict` reached **4/4 type-checking maturity**.
- The pinned command is `uv run --locked basedpyright --project
  pyrightconfig.strict.json`; it reports zero errors, warnings, and notes
  locally, with a zero strict-baseline delta.
- The intentional-failure fixture and occurrence-aware baseline checks remain
  in `tests/test_strict_debt.py`.
- Hosted CI run `33211556277` passed all quality and release-boundary jobs for
  commit `ca1b21f3264a504407248c6f231e2759900c2e3f`, providing the equivalent
  CI evidence required for promotion.
- The historical 4,192-diagnostic report is retained as historical context only;
  it is not current strict debt.

## Next Step

Merge PR #18 (`codex/strict-zero-pr-reconciliation`) into canonical `dev` after
review so the strict-zero implementation, release-boundary fix, and completed
maturity state become authoritative there. Keep the `v0.7.0` tag and PyPI
publication separate until the candidate is reviewed and promoted through the
documented release lane.

## Recent Progress

- 2026-08-28: `ca1b21f` completes the strict BasedPyright maturity promotion:
  the pinned local command reports zero diagnostics, the strict baseline delta
  is zero, the full suite passes 1,245 tests, the release boundary passes, and
  hosted CI run `33211556277` passes all eight jobs. The planning target is now
  recorded as complete; PR #18 remains open for canonical `dev` integration.
- 2026-08-01: The isolated `codex/main-fold-v0-7-0` candidate folds all
  semantically eligible branch tips through `189cbb7`. The ordinary suite
  passes 860 tests in 915.22 seconds and the LCOV-instrumented suite passes the
  same 860 tests in 678.52 seconds; Ruff, format, standard-mode BasedPyright,
  environment contract, Vulture, dependency audit, build, release smoke, and
  installed-wheel smoke pass. Timing failures exposed by the combined fold were
  repaired at their contract boundaries instead of waived.
- 2026-08-01: The missing public GitHub Release for the existing `v0.6.0` tag
  was created and verified without moving or recreating the tag; it still peels
  to `c6e92cc`. Ambiguous dirty worktrees and the stale command-surface branch
  remain preserved and unpruned.
- 2026-08-01: `6f22555` adds bounded fleet maturity/change-surface evidence,
  a replay-validated Pronto feed, isolated dependency preparation, and
  coverage-aware Codex Security evidence. The security adapter was split below
  the promoted large-source-file threshold; 30 focused tests, Ruff, format, and
  BasedPyright pass.
- 2026-07-21: `3952a54` aligns the packaged skill and detailed agent guide
  with canonical journeys, v2 outcomes, scan-scope controls, review/gate/
  planning/worker/rollout/release routes, and cache provenance; six focused
  documentation tests pass. A live origin refresh confirms the pushed branch
  alongside `dev` and `main`.
- 2026-07-21: `4b0c2ab` adds bounded/full-scan inclusion controls, protected
  path fail-closed behavior, inclusion provenance, and refresh/verify wiring;
  732 behavioral tests pass.
- 2026-07-17: `b5a610e` makes release-gate discovery preserve exact CI
  workflow commands; focused tests pass and exact-head GitHub CI is green.
- 2026-07-17: PR #5 merged v0.6.0 at `c6e92cc`; tag `v0.6.0`, release workflow
  run 13, PyPI publication, and a fresh public-install smoke all pass.
- 2026-07-17: `a3777b1` fixes release-profile discovery for dynamic version
  metadata and installed-wheel release smoke; its exact-head follow-up passes.
- 2026-07-17: `23da809` prepares v0.6.0 release metadata on the isolated
  release branch; the branch was later promoted and published as v0.6.0.
- 2026-07-17: `9107285` completes the `qr` command-surface cleanup: packaged
  alias parity, curated root help, README/CLI quickstart guidance, and focused
  help/version/JSON contract tests pass; the commit hook quality gate passed.
- 2026-07-13: v0.5.1 released: PR #2 merged at `a101bd4`, GitHub CI and tag
  release workflow pass, PyPI publishes both artifacts, GitHub Release is
  public, and a disposable PyPI install passes CLI, doctor, smoke, and MCP.
- 2026-07-13: `c71b130` completes pre-tag hardening: pinned pip-audit and
  pytest 9.0.3, validates baseline Git IDs before diffing, and passes the
  556-test release ladder plus installed-wheel smoke.
- 2026-07-13: `948107f` prepares v0.5.1 citation/changelog/upgrade metadata
  and README release guidance; pre-tag validation and publication remain.
- 2026-07-13: `141635e` closes the source-evidence follow-up: lexer-backed
  redaction protects private fields, malformed syntax, computed logs, and
  tokenless values; 554 tests and two independent reviews are clean.
- 2026-07-13: M7 completed in `279cc8a`: final redaction hardening covers
  multiline typed, concatenated, and template literals across code-quality,
  excerpts, and security candidates; built-wheel MCP execution is smoke-tested.
- 2026-07-13: M7 release hardening in `cd30948`: release tags must be reachable
  from `main`; CI/release and wheel tests exercise default v2 and frozen v1
  Review behavior; operator docs now disclose the old 0.5.0 display mismatch.
- 2026-07-13: M7 source-evidence hardening in `4dee5af`: shared redaction now
  protects security candidates, code-quality findings, and remediation excerpts
  across inspect, run, and verify without altering arbitrary artifact writes;
  `27deaa4` keeps that helper outside the security package to prevent cycles.
- 2026-07-13: M7 contract repair in `9fcea7d`: public positional verification
  and refresh slots are stable, Review v1 output/artifacts retain their frozen
  field shape, and the `ReviewFinding` façade is restored while default v2
  outcomes keep their explicit next action.
