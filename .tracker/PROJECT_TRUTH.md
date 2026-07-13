# Quality Runner Project Truth

Last updated: 2026-07-13

## Current State

The quality-skills audit contract is hardened on feature branch
`quality-skill-corpus-workflow` at commit `28905ca`. Release metadata now agrees on
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

## Next Step

Push and review `quality-skill-corpus-workflow`, then create the personal corpus
manifest and dogfood `skill classify`, `skill append`, and `skill sync` against
the selected repositories. Runtime/browser-dependent skills remain deferred.

## Blockers

- Full-repo Ruff/format and basedpyright retain pre-existing findings outside
  this change; touched-file checks pass. Vulture passes the source roots; its
  broad `vulture .` form needs `.quality-runner` excluded after local uv gate
  runs generate ignored dependency-cache code.

_(9 older entries trimmed)_

Current verification:

- 2026-07-13: Added personal corpus classification, pack append/provenance, and
  additive multi-repo synchronization in `28905ca`. Full suite passes (`423
  passed`); touched-file Ruff/format, BasedPyright, and Vulture pass. Full-repo
  Ruff and BasedPyright retain unrelated baseline findings.

- 2026-07-13: Aligned runtime, plugin, citation, and release-checklist
  metadata on `0.5.0` in `6e93ee0`; focused packaging checks and the full suite
  passed (`419 passed`). Touched-file Ruff/format and source-root Vulture pass;
  repository-wide Ruff/format/basedpyright retain unrelated baseline findings.
- 2026-07-13: Dogfooded the `0.5.0` runner against BBDSE, Portfolio, and Agent
  Eval Contract. Audit totals were 55, 29, and 12 respectively; dependency
  capability gaps cleared to zero after repo-local configuration. Agent Eval's
  dependency gate passed, BBDSE's gate reported advisories, and Portfolio's
  gate was blocked by pnpm build-script approval.

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
