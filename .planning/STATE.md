---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: GPT-5.6 modernization
status: complete
last_updated: "2026-11-03T21:13:00Z"
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

**Current focus:** Maintain proactive, project-owned performance acceptance in
the existing web-readiness path. Preserve strict typing and task release gates;
keep browser-producer trust, real-project adoption and publication explicit.

## Current Position

- Proactive web performance: optional lab receipt import and explicit repository
  budgets are implemented, with production build provenance, exact tracked HEAD,
  freshness, scenario, aggregation and policy checks. Missing measurements remain
  unknown. Build-file inventory is distinguished from route transfer.
- Scoped verification: 49 web-readiness tests pass, plus direct CLI pass,
  over-budget, stale and missing-evidence exercises. Full and release results
  belong to exact-current task receipts, not this historical summary.
- Existing performance reviews are refined in place in the portable starter;
  no universal targets, telemetry, browser dependency or fleet activation added.
- Real-repository pilot remains unverified due to unresolved workspace custody;
  fixture results do not establish application performance or field compliance.

### Prior dev reconciliation evidence

- Integration branch: `codex/qr-dev-reconciliation-20261102`, based on canonical
  `dev` at `a3670c6`; PR #18 is already merged there.
- Source history: `codex/qr-baseline-repair-20261102` at `b10c25a` is merged
  with both parent histories preserved. The change matrix retains both sides'
  records, and the fleet audit helper retains the strict-clean implementation.
- The combined source initially exposed 46 strict diagnostics, including a
  missing fleet import confirmed by a failing behavioral test. The repaired
  source reports zero strict diagnostics across 398 package files, and the
  pinned zero-baseline ratchet passes without changing the baseline.
- Local suite: 1,285 tests pass. Standard typing, Ruff lint and formatting,
  Vulture, dependency audit, environment contract, and secret scan pass.
- Exact-current task release and public package-boundary receipts are retained
  under the task's private evidence directory; do not infer their state from
  this historical planning summary.
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

- **Phase:** proactive-performance
- **Slug:** project-owned-web-budgets
- **Status:** Implemented; real-repository pilot blocked on workspace custody
- **Integration rule:** Promote only the reviewed candidate after its exact-current
  task release gate passes. Keep the existing zero-error CI ratchet enabled.

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

Continue development from the reconciled strict-clean `dev` history. Keep
standard and strict typing, the zero-baseline ratchet, and the authoritative
task release check in the verification path. The `v0.7.0` tag and PyPI
publication remain separate release actions requiring explicit approval.

## Recent Progress

- 2026-11-02: Reconciled canonical `dev` with the installed task/baseline-repair
  line. Resolved both merge conflicts, restored the fleet import, and checked
  dictionary containers before narrowing receipt and telemetry fields.
  Strict diagnostics are zero; all 1,285 tests pass. Updated stale guidance
  that still described strict mode as an unfinished migration. No strict
  configuration, baseline counts, ignores, or required gates were weakened.
- 2026-08-28: PR #18 merged at `a3670c6`; the strict-zero cleanup is canonical
  in `dev`. Earlier entries below describe their historical publication state.

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
