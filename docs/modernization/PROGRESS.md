# Modernization Progress

## Current state

M0 through M4 are implemented on the protected branch
`codex/gpt56-modernization`, based on `main` commit `0a3def1`. The branch
remains isolated until review and merge.

M0 restores the public trust boundary without changing artifact schema ids:

- package metadata now derives from `quality_runner/_version.py`; the plugin,
  wheel, CLI, MCP, and release-tag contracts are checked together;
- artifact, compatibility-certifier, explicit export, and rollout-output paths
  reject unsafe segments and symlinked ancestors or leaves;
- discovered gates are evidence-only by default; explicit execution requires a
  disposable checkout and is documented as arbitrary local code, not a sandbox;
- Fresh Review reports `packet-ready` or incomplete outcomes truthfully instead
  of resembling a completed no-findings review.

M1 establishes the typed migration seam without changing the v1 Fresh Review
projections:

- strict normalized packet, report, manifest, adapter, and known-issue records
  now live in `quality_runner.core`; application serializers own the v1
  projection boundary;
- public `review_types` and `review_context` retain their permissive v1 typed
  dictionary contracts, including direct combined packet callers;
- task, blind, combined, and direct-combined packet projections have committed
  M0 baseline fixtures, while v1 readers enforce their published closed-object
  schema boundaries;
- CLI and MCP review paths build strict internal values before persisting the
  identical v1 JSON artifacts.

M2 migrates the read-only audit vertical slice without changing the inspect/run
result schemas or artifact names:

- typed audit request, analysis, planning, and scoped-file contracts now sit
  behind one application use case; `workflow.inspect_payload` and `run_payload`
  are thin compatibility adapters;
- a v1 artifact renderer preserves the existing write order, including the
  intentionally different handoff, manifest, and final-result artifact-path
  snapshots;
- code-quality and security candidate analysis consume the same exclusion-aware
  bounded text scope, while a separately capped surface walk retains API,
  webhook, and dependency-manifest detection without polluting code-quality
  artifacts;
- the canonical API/webhook route predicate is shared by the collector and
  security scan, including `app/api`, `pages/api`, `src/routes`, `routes/api`,
  Go, Kotlin, and extensionless route paths.

M3 migrates gate verification without changing the public `verify-gates` result
schema or v1 artifact names:

- a typed verification request and execution policy now drive one application
  service, while `workflow_verify.verify_gates_payload` remains the thin CLI and
  refresh compatibility facade;
- M3 reuses M2 audit analysis, executes gates before planning, and renders the
  original plan-before-execution, partial-verification, intent, handoff, and
  manifest projections through a dedicated v1 artifact renderer;
- executable gates still require a disposable worktree, now receive only an
  explicit runtime environment allowlist, and clean up failed worktree creation
  and interrupted sessions without leaking tracked or untracked source files;
- timeout gate records are represented by the published schema, with regression
  coverage for environment secrecy, symlink refusal, cleanup, interruption, and
  the legacy intent artifact-path snapshot.

M4 adds a versioned journey-outcome layer without changing legacy CLI/MCP
projections:

- `quality-runner-outcome-v0.2` presents audit, review, verify, and bounded run
  history with explicit state, assessment, confidence, writes, safety, and one
  safest next action;
- `audit`, `verify`, and `runs` are outcome-first CLI journeys, while
  `review --outcome` is an explicit opt-in that preserves default v1 review
  behavior;
- four additive MCP tools expose the same contract as structured content while
  leaving legacy tools and schemas unchanged;
- safety claims are derived from observed branch/execution evidence, malformed
  verification artifacts fail closed, and unavailable history is limited
  evidence rather than a clean no-history result;
- legacy workflow access is isolated behind explicit compatibility adapters, and
  v2 schema, projection, CLI, MCP, history, and adversarial regression tests
  hold the cross-journey contract.

## Decisions in force

- Use a parallel typed core with controlled adapters, not a clean rewrite.
- Treat the CLI/MCP workflow as the primary interface; do not build a web UI as
  part of this modernization.
- Preserve public artifact and compatibility contracts while making execution
  safer by default.
- Keep `CITATION.cff` on the last published release until the tagged release
  commit updates it; the tag workflow verifies that parity explicitly.
- Treat v1 payloads and Python typed dictionaries as compatibility projections;
  strict core contracts must not leak into legacy entrypoint annotations.

## Quality status

- The full `pytest` suite passes (496 tests); Basedpyright reports zero errors.
- Ruff lint/format, Vulture, a fresh package build, and
  `quality-runner release-smoke --json` pass.

## Next milestone

M5 makes Fresh Review operationally honest from packet creation through adapter
response validation and fixing handoff, retaining packet-only review as a clear
distinct capability.
