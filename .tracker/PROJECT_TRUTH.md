# Quality Runner Project Truth

Last updated: 2026-07-16

## Current State

The native QR phase-planning contract shipped in `1f44c21`. Quality Runner now
owns evidence-backed phase and plan documents under `.planning/quality-runner/`,
including deterministic waves, dependency metadata, next-plan dispatch, batch
result recording, remediation-delta updates, and phase verification. QR still
does not execute source changes, create commits, push branches, or modify root
GSD files; GSD remains an optional external consumer.

The tool-neutral `remediation-delta` contract shipped in `b50413a`. Quality
Runner compares QR runs and emits evidence updates without requiring GSD.

The quality-skills audit contract is hardened on feature branch
`quality-skill-corpus-workflow` at commit `b879c63`. Release metadata now agrees on
version `0.5.0` across the runtime package, wheel manifest, citation record,
and release checklist. The source-backed user packs
`ui-foundations`, `test-strategy`, `security-privacy`, `release-readiness`,
`pr-risk`, `data-integrity`, `developer-experience`, and
`architecture-maintainability` now cover visual and UI-state risks, behavior
coverage, regression value, test reliability, transport and cross-origin risks,
authorization, privacy flows, input boundaries, security evidence, release
verification, compatibility, rollback, changed-surface risk, merge integrity,
schema and migration safety, pipeline correctness, onboarding, wayfinding,
contribution flow, ownership, duplication, boundaries, and handoff through
deterministic observations and high-recall agent reviews. SQL is now included in
Quality Runner's text scan surface for migration audits. The UI Foundations
empty-state trigger now requires data-shaped collection identifiers for `.map()`
matches, avoiding static navigation-list noise while preserving fetch/query
triggers and agent-review coverage.
The Architecture and Maintainability compatibility trigger now requires
code-shaped seam declarations or compatibility terms paired with boundary
language, avoiding generic documentation/configuration mentions.
The core security scanner's secret-in-fallback candidate now requires a
credential-shaped name or recognizable token marker, preserving the secret
review gate while filtering ordinary UI, error, content-type, and demo defaults.
Run artifacts now support configured regex redaction for JSON/Markdown writes,
dry-run-first retention pruning, and redaction-safe gate-run persistence. The
repository config declares an executable `security_dependency_audit` gate that
exports the locked dependency set and runs `pip-audit` without auditing the
editable local project. Final dogfood reports that gate as passed through the
Quality Runner executor. The full test suite now passes with `419 passed`
after aligning the runtime version and packaged metadata on `0.5.0`.
Fresh `0.5.0` dogfood also ran against BBDSE, Portfolio, and Agent Eval
Contract. All three now report zero missing dependency-audit capabilities after
repo-local gate configuration: Agent Eval's lockfile audit passed, BBDSE's gate
surfaced real high/critical JavaScript advisories, and Portfolio remains blocked
before audit execution by its existing interactive `pnpm approve-builds`
requirement. BBDSE and Portfolio now ignore generated `.quality-runner/cache/`
trees. Personal Quality Skill corpus management now has a versioned
`quality-runner-corpus.toml` manifest, advisory pack classification, explicit
append-to-existing-pack with namespaced rule/review ids and `[[sources]]`
provenance, and additive dry-run-first multi-repository synchronization. Raw
Markdown skills remain ingest inputs; only validated compiled TOML packs sync.
The mined anti-template workflow now has clean-room `ui-specificity` and
`copy-specificity` starter packs, preserves `skill:<id>` categories through the
audit/actionability boundary, rejects invalid regexes during skill ingest, and
scans Astro, Vue, Svelte, SCSS, Sass, Less, and MDX surfaces. These packs remain
opt-in observations with contextual review and rendered/copy verification.

The QR-native similarity backend shipped in `a7b45ab`, with focused Python
coverage added in `795c8f2`. Quality Runner now owns
the default standard-library similarity scan for JavaScript/TypeScript, Python,
and Rust, with a stable `quality-runner-similarity-v0.1` report schema and an
explicit `similarity_backend` configuration choice. The upstream-compatible
binary scanners remain an opt-in external adapter; QR never installs them, and
missing external binaries remain report-only scanner status. The native path is
covered by focused tests and does not vendor upstream source.

The module-status contract is now wired through inspect, run, verify, refresh
timeouts, manifests, summaries, status output, and human CLI output. Core
similarity and detected UI quality are reported explicitly, while contextual
layers such as UI token contracts, architecture contracts, Quality Skills,
release readiness, intent, CI evidence, QR Gate, and QR phase planning retain
visible `enabled`, `disabled`, `not_applicable`, `unavailable`, or `not_run`
states. The status projection is versioned as
`quality-runner-module-status-v0.1`, and the scan summary stays within the
repository's 500-line source-file ceiling.

Configured active Quality Skill packs now participate in every selected QR
workflow automatically: deterministic rules run during the scan, while every
active agent-review rubric is emitted as an automatic supervising-agent work
item. The report contract requires explicit coverage of every rubric, including
clean subjective outcomes, before the report can merge. The default review mode
is `auto`; `release` still forces `required`, and `off`/`parallel` remain
explicit opt-outs. The supervising agent submits the validated report with
`--skill-review-report`, including when continuing through `refresh`.

Read-only integrity snapshots now skip standard dependency, cache, build, and
generated trees, honor configured scan exclusions, and use bounded fingerprints
for large remaining files. A live Tenure snapshot completed in 0.20 seconds
without recording `node_modules`; the full QR test suite passed (`472 passed`).

Global compiled Quality Skill selection is now available for every repository
without requiring a repository-local pack block. QR discovers the user-level
configuration, derives repository signals, selects relevant compiled TOML packs
with local precedence and explicit opt-out/pin controls, and records candidate
scores, exclusions, corpus identity, and warnings in the code-quality artifact.
Raw global Markdown skills remain ingest inputs rather than silently executable
workflow instructions.

The user-level corpus is now installed at
`~/.config/quality-runner/corpus` with an explicit
`~/.config/quality-runner/quality-runner.toml` selector. All 12 validated
starter packs are eligible in `relevant` mode with a bounded maximum of 12;
repository signals choose the active subset. Global selection preserves
matched signal terms for artifact replay, and review-packet reconstruction
uses the captured accountability paths so selected agent reviews remain
actionable on large repositories.

Remediation planning now defaults to a deterministic domain view. Each run
emits `phase_candidates` for security, data integrity, quality gates, testing,
release readiness, UI quality, performance, maintainability, and other detected
workstreams while retaining the complete leaf `slices` list for forensic scope
and cold-executor specs. QR-native `phase plan` consumes domain candidates when
present and falls back to leaf slices for older artifacts; QR still does not
write GSD-owned files or execute remediation.

Long-running workflow commands now emit phase diagnostics and 15-second
heartbeats to stderr while preserving a single machine-readable JSON document
on stdout. The progress channel covers inspect, run, verify-gates, refresh, and
release-smoke; callers with their own status channel can use `--no-progress`.

## Next Step

Dogfood the active Quality Skill handoff contract against representative UI,
test, security, and release repositories so agents consume packets and
complete the explicit report-and-rerun loop. Use
`quality-runner plan auto <repo> --run-id <run-id> --json` as the default
planning layer; it materializes domain phases in deterministic security-first
order and retains linked leaf slices. GSD remains optional and independent.

## Blockers

- Full-repo Ruff passes. Full format check reports 25 pre-existing files
  outside this slice, and full basedpyright reports 14 pre-existing errors in
  review files; touched-file checks pass. Vulture passes the source roots; its
  broad `vulture .` form needs `.quality-runner` excluded after local uv gate
  runs generate ignored dependency-cache code.
- The packaged console-script smoke requires a writable UV cache and network
  access when the offline wheel build cannot reuse dependencies; it passed with
  a temporary cache. Full-repo Ruff and basedpyright remain blocked by the
  pre-existing findings listed above.
- The full test suite currently passes (`500 passed`). Full-repo format and
  basedpyright still need a separate clean-tree pass because the branch carries
  unrelated user changes outside this slice.
- The feature branch still contains unrelated user changes outside `a7b45ab`;
  no push or merge was attempted for this isolated commit.

## Current Verification

- 2026-07-16: Added seamless automatic skill-review coverage and native
  security-first phase materialization. The default `auto` mode now requires
  every active skill/review pair to be covered, including clean subjective
  outcomes; `quality-runner plan auto` is idempotent and retains linked leaf
  slices. Full suite passed (`500 passed`), full Ruff passed, touched-slice
  format and BasedPyright passed (`0 errors`), and release-smoke passed with
  installed artifact digest `ea438ad0fc5b904f56d5fb6eb3f8af8a21328a0681ac5230a4ee6581cbc4e2f3`.

- 2026-07-16: Reran the default QR workflow against Tenure on
  `codex/port-review-hardening` as `domain-default-20260716`. The run completed
  in 240.4 seconds with 5,900 structural findings, 10 selected global packs,
  956 total leaf slices, and 10 domain phase candidates. The handoff remains
  `review-required` because the skill-review packet has unresolved reviews;
  domain grouping and schema validation passed, while the existing handoff
  quality lint still reports six skill-slice verification gaps.

- 2026-07-16: Final repository verification after domain planning changes:
  full suite passed (`500 passed`), touched-source Ruff, format, and
  BasedPyright passed (`0 errors`), scoped Vulture passed, and
  `quality-runner release-smoke --json` passed with installed artifact digest
  `ea438ad0fc5b904f56d5fb6eb3f8af8a21328a0681ac5230a4ee6581cbc4e2f3`.

- 2026-07-16: Added deterministic domain phase candidates to remediation plans
  and handoffs while retaining leaf slices for forensic execution. Native QR
  phase planning now prefers domain candidates and remains backward-compatible
  with v0.1 leaf-only artifacts. Domain/schema/planning focused coverage passed
  (`64 passed`), touched-source Ruff/format/BasedPyright passed, and Vulture
  passed.

- 2026-07-16: Added stderr-only phase and heartbeat progress for long-running
  CLI workflows, with JSON stdout preserved and `--no-progress` suppression.
  Focused progress/CLI coverage passed (`32 passed`), full suite passed
  (`480 passed`), full Ruff check passed, targeted BasedPyright passed with
  `0 errors`, and scoped Vulture passed.

- 2026-07-16: Repository-aware global Quality Skill selection passed focused
  contract coverage (`68 passed`), targeted BasedPyright (`0 errors`), Ruff,
  and scoped Vulture. The full suite passed (`477 passed`); entrypoint and
  release-smoke tests passed (`9 passed`); and `quality-runner release-smoke
  --json` passed after installing and exercising the local wheel, recording
  artifact digest `571c732e83d5dc49391650ab686df02e7490ab7289fb66ce8749eefa27a8ac12`.

- 2026-07-16: Fixed read-only integrity scope so dependency, cache, and
  generated trees such as `node_modules` and `.next` are pruned before
  manifesting; configured scan exclusions are forwarded from gate verification,
  and large files use bounded fingerprints. Integrity/gate tests passed (`23
  passed`); full suite passed (`472 passed`), full Ruff passed, and a live Tenure
  snapshot completed in `0.20s` with no `node_modules` paths.

- 2026-07-16: Configured active skill packs now run deterministic rules
  automatically and emit review packets; unresolved agent reviews produce
  `review-required` handoffs and blocked lifecycle status, while validated
  reports pass through refresh. Focused skill/config/refresh coverage passed
  (`64 passed`), full suite passed (`471 passed`), touched-source Ruff and
  format passed, targeted BasedPyright passed with `0 errors`, scoped Vulture
  passed, schema parsing passed, and `release-smoke --json` passed with an
  installed artifact consumer digest.

- 2026-07-16: Extended the QR-native similarity contract with explicit core and
  UI module statuses, artifact/manifest/summary/status wiring, timeout status
  coverage, and human CLI summaries. Focused similarity/module tests passed;
  touched-source Ruff, formatting, and basedpyright (`0 errors`) passed. Full
  suite verification passed (`467 passed`), with `code_quality.py` held at the
  500-line ceiling.

_(6 older entries trimmed)_

- 2026-07-12: Added and committed the `ui-foundations` starter pack as
  `ed16bb2`. Focused quality-skill tests passed (`24 passed`), pack ingest,
  touched-file Ruff, format, and agent-review report merging passed. Full suite
  reached `402 passed, 1 failed` on the existing packaging-entrypoint mismatch.

- 2026-07-12: Added and committed the `test-strategy` starter pack as
  `8055088`. Focused quality-skill tests passed (`25 passed`), pack ingest,
  touched-file Ruff, format, and agent-review report merging passed. Full suite
  reached `403 passed, 1 failed` on the existing packaging-entrypoint mismatch.

- 2026-07-12: Added and committed the `security-privacy` starter pack as
  `140e1f8`. Focused quality-skill tests passed (`26 passed`), pack ingest,
  TOML parsing, touched-file Ruff, format, and agent-review report merging
  passed. Full suite reached `404 passed, 1 failed` on the existing
  packaging-entrypoint mismatch.

- 2026-07-12: Added and committed the `release-readiness` starter pack as
  `c79de7e`. Focused quality-skill tests passed (`27 passed`), pack ingest,
  TOML parsing, touched-file Ruff, format, and agent-review report merging
  passed. Full suite reached `405 passed, 1 failed` on the existing
  packaging-entrypoint mismatch.

- 2026-07-12: Added and committed the `pr-risk` starter pack as
  `56b2ec0`. Focused quality-skill tests passed (`28 passed`), pack ingest,
  TOML parsing, touched-file Ruff, format, and agent-review report merging
  passed. Full suite reached `406 passed, 1 failed` on the existing
  packaging-entrypoint mismatch.

- 2026-07-12: Added and committed the `data-integrity` starter pack as
  `e940bb0`, including SQL text discovery for migration audits. Focused
  quality-skill tests passed (`29 passed`), pack ingest, TOML parsing,
  touched-file Ruff, format, and agent-review report merging passed. Full suite
  reached `407 passed, 1 failed` on the existing packaging-entrypoint mismatch.

- 2026-07-12: Added and committed the `developer-experience` starter pack as
  `81efe8b`. Focused quality-skill tests passed (`30 passed`), pack ingest,
  TOML parsing, touched-file Ruff, format, and agent-review report merging
  passed. Full suite reached `408 passed, 1 failed` on the existing
  packaging-entrypoint mismatch.

- 2026-07-12: Added and committed the `architecture-maintainability` starter
  pack as `4724fcc`. Focused quality-skill tests passed (`31 passed`), pack
  ingest, TOML parsing, touched-file Ruff, format, and agent-review report
  merging passed. Full suite reached `409 passed, 1 failed` on the existing
  packaging-entrypoint mismatch.

- 2026-07-12: Added and committed the `performance-readiness` starter pack as
  `3e84ce5`. Focused quality-skill tests passed (`32 passed`), pack ingest,
  TOML parsing, touched-file Ruff, format, and agent-review report merging
  passed. Full suite reached `410 passed, 1 failed` on the existing
  packaging-entrypoint mismatch.

- 2026-07-12: Added and committed the `motion-quality` starter pack as
  `2470008`. Focused quality-skill tests passed (`33 passed`), pack ingest,
  TOML parsing, touched-file Ruff, format, and agent-review report merging
  passed. Full suite reached `411 passed, 1 failed` on the existing
  packaging-entrypoint mismatch.

- 2026-07-12: Quality-skills hardening committed as `ccfc12e`. Focused skill and
  workflow tests passed (`25 passed`); full suite reached `401 passed, 1 failed`
  on the existing packaging-entrypoint mismatch. Touched-file Ruff, format,
  targeted basedpyright (`0 errors`), schema JSON parsing, vulture, and the
  commit-hook Pre-CR check passed.

- 2026-07-07: Prepared `0.4.0` release after extracting structural-scan and
  similarity parser modules, fixing controller-report batch-scope assembly, and
  clearing full-repo `uv run ruff check .` and `uv run basedpyright`. Verified
  with full `uv run pytest -q` (362 passed), `uv run ruff format --check .`,
  `uv run --with vulture vulture . --min-confidence 70`, and
  `quality-runner release-smoke --json`.
- 2026-07-07: Added `integrate` unwired-work detection, dead-code output
  reinterpretation, and decision-based remediation slices that ask authors to
  wire, finish, descope, or accept WIP. Verified with focused unwired-work
  tests (`uv run pytest -q tests/test_code_quality_unwired.py
  tests/test_unwired_from_dead_code.py tests/test_remediation_wiring.py
  tests/test_config.py tests/test_phase1_semantics.py
  tests/test_workflow.py::test_run_payload_adds_structural_findings_and_groups_remediation_slices
  tests/test_code_quality.py::test_quality_runner_source_files_stay_under_default_large_file_threshold`),
  full `uv run pytest -q`, touched-file `uv run ruff check ...`, and
  `uv run --with vulture vulture . --min-confidence 70`.
- 2026-07-04: Documented the AIOS launch shortcut in the rollout controller
  notes. Verified with `uv run pytest -q tests/test_rollout.py
  tests/test_release_docs.py` and `uv run ruff check docs/qr-rollout-20260702.md`
  (Ruff reported no Python files under the Markdown path and exited cleanly).
- 2026-07-04: Added DOI-ready software-methods metadata and release notes.
  Verified the passing DOI path with `uv run ruff check quality_runner tests`,
  `uv run pytest -q`, and `uv run quality-runner release-smoke --json`.
  DOI minting is still blocked by existing format drift in five files and
  existing basedpyright debt in tests.
- 2026-07-04: QR now excludes generated artifact surfaces from both recursive
  discovery and structural source scanning: build/test outputs, local caches,
  top-level artifact output dirs, lockfiles/build metadata, and
  `generated-*` source artifacts. Verified with regression tests, full
  `uv run ruff check .`, `uv run basedpyright`, full `uv run pytest -q`, and a
  non-mutating BBDSE `BBDS-Analytics-Product-Suite` smoke where discovery took
  0.544s and code-quality scanning took 6.437s.
- 2026-07-04: `quality-runner rollout` now writes fleet planning documents by
  default: `per-repo-summaries/INDEX.md`, one per-repo summary document per
  rollout entry, and `fleet-remediation-phases.md`. Verified with focused
  rollout tests, focused ruff on rollout/document files, `uv run basedpyright`,
  and full `uv run pytest -q`. Full `uv run ruff check .` is currently blocked
  by a pre-existing dirty scan-exclusion import-order issue outside this
  rollout-document change.
- 2026-07-04: Branch-scan warnings now compare commit identity, so a checked
  out `dev` branch aligned to `main` does not emit
  `checked_out_branch_not_main_or_most_advanced`. Verified with the focused
  branch workflow tests, a full `uv run pytest -q`, and a real QR run against
  `agent-eval-contract` that returned no warnings.
- 2026-07-04: `uv run ruff check .`, `uv run basedpyright`, and
  `uv run pytest` passed after the README install documentation update.

## QR Remediation Planning

- 2026-07-04: Added GSD Phase 1 for QR remediation from qr-fleet-continue-20260704-quality-runner; 1 plan(s) created from quality-runner.md. Execution has not started.
