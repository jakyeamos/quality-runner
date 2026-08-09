---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: GPT-5.6 modernization
status: complete
last_updated: "2026-08-01T20:02:01Z"
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
    status: blocked
    interim_gate: basedpyright-standard-full-package
    observed_strict_errors: 4192
    promotion_requirement: occurrence-aware ratchet or zero strict diagnostics with repeatable local and CI evidence
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

- Branch: `codex/qr-flexible-scan-scope`
- Baseline: `dev` at commit `ca2e34b`; implementation commit `4b0c2ab`,
  instruction audit commit `3952a54`, governed fleet and security evidence
  commit `6f22555`
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

## Outstanding Maturity Target

- `basedpyright-strict` remains required for **4/4 type-checking maturity**.
- The passing full-package standard BasedPyright command is the certified
  interim gate, not the terminal maturity state.
- The last strict-mode trial reported 4,192 existing diagnostics, so strict
  enforcement is blocked; the target must not be removed or marked complete
  because standard mode passes.
- Promotion requires a pinned, repeatable full-package strict command with
  equivalent local and CI evidence, an intentional-failure fixture, and either
  zero strict diagnostics or deterministic occurrence-level baselining that
  blocks new diagnostics without treating persisted legacy debt as new.
- Reassess this target after the `0.7.0` fold and before any claim that
  type-checking has reached 4/4 maturity.

## Next Step

Publish this source branch for provenance, fold it into the isolated
`codex/main-fold-v0-7-0` candidate, and keep tag/PyPI publication separate
until the candidate is on the verified canonical `main`.

## Recent Progress

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
