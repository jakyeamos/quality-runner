# Modernization Execution Plan

## Strategy: parallel v2 core with controlled adapters

Build the new core alongside the existing implementation and migrate complete
user journeys through it. This protects durable public contracts while avoiding
another layer of patches in the current orchestration code. A clean rewrite is
rejected because artifact schemas, MCP consumers, and compatibility packages are
active contracts; a deep refactor in place is rejected because it would mix
safety fixes, behavior changes, and structural migration without a stable
comparison point.

Every milestone ends runnable, has a focused contract suite, and is committed as
one atomic change. New and old paths may coexist only behind an explicit adapter
or compatibility projection; once all consumers migrate, the obsolete path is
deleted in the same milestone or scheduled in the published deprecation plan.

## Milestones

### M0 — Restore trust at the boundary

- **Objective:** fix release identity and the confirmed high-risk path/execution
  gaps before expanding the codebase.
- **Systems:** package metadata, artifact resolver/persistence, verification
  policy, compatibility CLI, release tests, threat model, and CI.
- **Preserve:** current artifact semantics and public script names.
- **Change intentionally:** unknown gate commands stop executing by default;
  `review-not-run` becomes a distinct packet-ready result.
- **Verify:** package wheel/runtime/plugin version parity; traversal and symlink
  regression fixtures; policy tests for unknown commands; installed-wheel smoke.
- **Rollback:** revert the isolated patch set; artifacts remain v1-compatible.
- **Likely failure:** tightening path or execution rules rejects a legitimate
  workflow. The failure must name the required explicit opt-in, not fall back
  silently.

### M1 — Establish v2 contracts and a migration harness

- **Objective:** introduce typed input/output contracts, stable serializers, and
  golden fixtures without moving a user journey yet.
- **Systems:** new core/application packages, schema serializers, test fixtures,
  release-contract checks.
- **Depends on:** M0.
- **Preserve:** every v1 JSON and MCP projection exactly.
- **Change intentionally:** new internal code stops passing unconstrained
  dictionaries across use-case boundaries.
- **Verify:** fixture round trips, v1/v2 projection comparisons, import-cycle
  checks, and basedpyright on the new boundaries.
- **Rollback:** remove the unused v2 core; no persisted v2 state is required.
- **Likely failure:** over-modeling every legacy payload. Start with boundary
  types and leave private rule internals behind a narrow interface.

### M2 — Migrate the read-only audit vertical slice

- **Objective:** run discovery, standards, capabilities, security, code-quality,
  planning, and artifact rendering through one typed audit use case.
- **Systems:** pipeline composition, scanner registry, artifact writer, CLI/MCP
  audit adapters.
- **Depends on:** M1.
- **Preserve:** existing inspect/run artifacts, finding IDs, and handoff
  expectations.
- **Change intentionally:** deterministic analysis is separated from filesystem
  persistence; scans share exclusions and resource budgets.
- **Verify:** corpus fixtures, byte/line budget tests, CLI/MCP goldens, and
  artifact manifest comparisons.
- **Rollback:** route adapters back to the v1 implementation; retained v1
  artifacts stay readable.
- **Likely failure:** a v2 serializer subtly changes a consumer-visible field.
  Gate cutover on byte-aware semantic fixture diffs, not happy-path tests alone.

### M3 — Migrate verification as an isolated vertical slice

- **Objective:** make gate verification a single explicit policy-controlled
  application service.
- **Systems:** execution policy, subprocess runner, Git worktree handling,
  verification artifacts, CLI/MCP adapters.
- **Depends on:** M0 and M2.
- **Preserve:** known-safe gate support, evidence output, and explicit
  disposable-checkout execution.
- **Change intentionally:** disposable verification is the only executable
  mode; read-only rollback is no longer presented as a complete sandbox.
- **Verify:** hostile config, environment minimization, timeout, untracked-write,
  worktree cleanup, and recovery-after-interruption fixtures.
- **Rollback:** disable the new executable mode while retaining scan-only audit;
  never re-enable arbitrary execution implicitly.
- **Likely failure:** a real project needs a capability absent from the minimal
  environment. Add a named, audited capability rather than copying the parent
  environment wholesale.

### M4 — Ship the journey-led CLI and MCP outcome model

- **Objective:** make common audit, review, verify, and run-history journeys
  discoverable without losing programmatic compatibility.
- **Systems:** CLI parser/renderer, help and examples, MCP tool descriptions,
  outcome schemas, README and operator docs.
- **Depends on:** M2 and M3.
- **Preserve:** legacy commands and output projections through adapters.
- **Change intentionally:** command results lead with state, confidence, writes,
  safety mode, and next action; advanced operations move behind progressive
  help or namespaced paths.
- **Verify:** plain-text snapshots, JSON/MCP compatibility fixtures, task-based
  usability scripts, and documented no-review/blocked/error states.
- **Rollback:** keep legacy aliases and opt clients back to legacy rendering.
- **Likely failure:** aliases conceal a semantic change. Emit targeted
  deprecation notices and require explicit format/mode selection where needed.

### M5 — Make Fresh Review operationally honest

- **Objective:** complete the review packet, adapter, response validation, and
  fixing-handoff flow as one end-to-end slice.
- **Systems:** review context/report/state, adapter protocol, CLI/MCP review
  adapters, artifact renderers, user documentation.
- **Depends on:** M1 and M4.
- **Preserve:** local-first packet generation and the independent reviewer/fixer
  boundary.
- **Change intentionally:** no-adapter runs report packet readiness, not zero
  findings; documented defaults and implemented flags become one contract.
- **Verify:** task/blind/combined fixtures, no-adapter UX snapshots, malicious
  adapter output validation, and loop state-transition tests.
- **Rollback:** packet-only review remains a valid distinct capability.
- **Likely failure:** a “fresh” review receives prior context through a hidden
  path. Test provenance and exclusions explicitly.

### M6 — Isolate compatibility and retire duplicate foundations

- **Objective:** move legacy certifier and legacy workflow projections behind
  explicit compatibility adapters, then delete duplicate orchestration.
- **Systems:** compatibility packages, plugin metadata, scanner rule interfaces,
  legacy workflow modules, release tests.
- **Depends on:** M2 through M5.
- **Preserve:** installed imports, scripts, MCP tool metadata, and documented
  v1 artifact projections during the deprecation window.
- **Change intentionally:** the v2 core becomes the only new implementation
  path; legacy modules become thin adapters or are removed when unreferenced.
- **Verify:** installed-wheel compatibility smoke, import/API fixtures, static
  dependency checks, and dead-code scan after each removal.
- **Rollback:** adapters target a tagged v1 implementation; artifacts remain
  versioned and reversible.
- **Likely failure:** an undocumented external import exists. Publish a clear
  compatibility window and retain telemetry-free manual migration guidance.

### M7 — Release, cut over, and harden

- **Objective:** make the new system the default, document its guarantees, and
  establish repeatable release evidence.
- **Systems:** packaging, Homebrew/release docs, CI, threat model, upgrade guide,
  deprecation notices, operational troubleshooting.
- **Depends on:** M6.
- **Preserve:** explicit migration/rollback instructions and v1 readers for the
  promised window.
- **Change intentionally:** v2 outcome rendering becomes the default for new
  clients; legacy paths carry a versioned warning.
- **Verify:** full matrix, isolated real-repository smoke, built-wheel install,
  security regression suite, artifact upgrade/downgrade checks, and doc-to-code
  review.
- **Rollback:** select the prior tagged release or legacy adapter format; do not
  delete v1 artifact readers until the public window closes.
- **Likely failure:** release docs drift again. Generate verification evidence
  from the built distribution, not source-only assumptions.

## Cutover and cleanup rules

1. V2 serializers are additive until their consumers are proven migrated.
2. A compatibility adapter has one owner and a sunset version; it is not a
   permanent second implementation.
3. The only allowed safety fallback is to a more restrictive mode.
4. Each cutover compares baseline and candidate fixtures, then re-runs the full
   release suite in a fresh worktree.
5. Delete old modules, tests, docs, flags, and dependencies only once their
   adapter has no remaining consumer and its replacement has passed the release
   suite.

## Product defaults recorded for implementation

- Unknown discovered commands require explicit execution consent and run in a
  disposable checkout. The checkout is not an arbitrary-command sandbox.
- Legacy public surfaces receive two minor releases of compatibility support
  after a v2 default ships, unless a security fix requires earlier restriction.
- No browser dashboard or optional TUI is built before the CLI/MCP journeys are
  demonstrably clear and trustworthy.
- New production dependencies require a written rationale and an exit strategy.
