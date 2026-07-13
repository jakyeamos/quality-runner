# Quality Runner Project Truth

Last updated: 2026-07-13

## Current State

Quality Runner is a public, local-first quality orchestration package. It
inspects repositories, records evidence, plans remediation, and hands execution
to separately authorized humans or agents. It does not own autonomous source
changes or remote review execution.

`main` is the 0.5.0 release baseline. The protected
`codex/gpt56-modernization` branch contains M0 trust-boundary work in
`f36dcf4`, M1 typed Fresh Review contracts in `cb12746`, M2 typed read-only
audit orchestration in `3f23204`, and M3 typed verification orchestration in
`8705cc1`. M4 in `75d8ac4` adds the additive v2 journey-outcome contract,
outcome-first CLI/MCP surfaces, bounded run history, and precise safety
projections. M5 in `f5c8610` completes the two-phase Fresh Review lifecycle:
strict packet-bound local responses, isolated combined packets, auditable
handoffs, and truthful artifact/outcome reporting. The branch is an unreleased
0.5.1 candidate; no tag or package publication has occurred. M6 began in
`0b5ac2e`: application-owned audit, verification, and journey services now sit
behind explicit workflow and outcome façades, with installed-wheel facade
checks. M6 completes in `56c94d4`: packet construction and report normalization
now have application owners, while root review façades retain their v1 type and
direct-combined compatibility contracts. M7 is complete: `113f143` redacts
secret-like candidate literals before they are fingerprinted or persisted, and
`66ce3ef` locks the development toolchain while testing doctor, v2 outcomes,
and MCP discovery from the built wheel. `32e7b26` makes CLI Fresh Review v2
outcome-first, with an explicit stderr-noticed v1 projection through 0.7.x;
the MCP v1 tool remains a separate compatibility surface. `633b96e` records
candidate-aware upgrade, rollback, release, and sensitive-artifact guidance.
`dc09ec0` proves that a default v2 Review run still persists v1-readable
context, manifest, and report artifacts. `9fcea7d` restores legacy positional
workflow slots, freezes the published v1 Review field shape, and re-exports the
public `ReviewFinding` type while retaining explicit v2 next-action guidance.
`4dee5af` shares redaction across security candidates, code-quality findings,
and remediation excerpts so source-secret markers do not persist in those paths;
`27deaa4` moves the helper to a neutral module to preserve the import boundary.
`cd30948` requires release tags to be ancestors of `main`, smoke-tests default
v2 and frozen v1 Review behavior from installed wheels, and corrects the
release, rollback, and Homebrew guidance. M7 completes in `279cc8a`: source
evidence redaction now covers multiline typed, concatenated, and template
literals across code-quality, remediation excerpts, and security candidates;
CI/release and installed-wheel tests execute the MCP v2 Review outcome.
Independent post-M7 review found four P2 release blockers. `bf6c9e7` closes
the source-evidence redaction bypasses for typed, commented, and expression
assignments; the branch remains unmerged while the remaining schema and
operator-documentation repairs are completed and revalidated.

## Current Position

- Target: a typed v2 core behind CLI, MCP, and compatibility adapters.
- Next implementation slice: finish the remaining independent-review P2
  repairs, repeat the release gate, then fast-forward merge only when no
  P0/P1/P2 findings remain.
- Canonical planning documents: `docs/modernization/`.
- Public compatibility: retain `quality_evidence_contract` and
  `repo_quality_certifier` during a published transition window.

## Core Contract

- Local-first operation with no silent remote transfer.
- Auditing/planning stays separate from source mutation.
- JSON artifacts remain canonical; Markdown remains the human decision surface.
- Scan-only and code-executing verification are explicit, separately reported
  modes.
- Primary CLI journeys are outcome-first; legacy JSON is an explicit supported
  compatibility projection rather than a silent default.

## Baseline Quality

- The M7 full 533-test pytest suite, Ruff lint/format, Basedpyright, Vulture,
  lock validation, YAML validation, package build, and release smoke passed.
  The post-review source-redaction regression suite passes; full release
  validation remains required after the remaining P2 repairs.
- Basedpyright reports zero errors; audit, review, verify, and run history now
  have a versioned v2 outcome contract behind preserved v1 projections.
- Release smoke now checks package/runtime/plugin parity and the release
  workflow enforces tag, wheel, manifest, citation, and MCP outcome contracts.

## Risks

- Generated evidence can contain target-repository output; it remains local and
  must be handled as potentially sensitive even after source-evidence redaction.
- Existing large-file warnings remain in `repo_quality_certifier/core.py` and
  `tests/test_cli.py`.
- User-authored gate commands remain arbitrary code; M0 requires explicit
  consent and a disposable checkout but does not sandbox those commands.
- Combined file-adapter task provenance remains the baseline-compatible string
  `"None"` until a published compatibility cutover can change that projection.

## Recent Progress

- 2026-07-13: Independent merge review found four P2s. `bf6c9e7` closes
  typed/commented/expression source-evidence redaction gaps; versioned gate
  schema and release-documentation repairs remain in progress.
- 2026-07-13: M7 completed in `279cc8a`: context-aware redaction covers
  multiline source evidence and security candidates; built wheels smoke the MCP
  Review outcome as well as default v2 and frozen v1 CLI output.
- 2026-07-13: `cd30948` adds `main`-ancestry release gating, built-wheel Review
  projection checks, and accurate historical rollback/Homebrew documentation.
- 2026-07-13: `4dee5af` closes the source-evidence redaction bypass across
  code-quality, slice-enrichment, and security candidate artifacts; `27deaa4`
  resolves its package-cycle regression.
- 2026-07-13: `9fcea7d` restored positional workflow compatibility, the frozen
  Review v1 field shape, and the `ReviewFinding` facade without weakening the
  default v2 packet-ready outcome.
- 2026-07-13: M7 compatibility regression in `dc09ec0`: default Review
  outcomes retain v1-readable persisted artifacts for downgrade safety.
- 2026-07-13: M7 guidance in `633b96e`: canonical upgrade/rollback policy,
  release evidence, and artifact-sensitivity guidance now match the cutover.
- 2026-07-13: M7 cutover in `32e7b26`: CLI Review defaults to v2, retains
  `--legacy-output` v1 JSON through 0.7.x, and documents legacy MCP discovery.
- 2026-07-13: Began M7 in `113f143`: security candidates redact secret-like
  literals before fingerprints and persisted scan/audit/handoff evidence.
- 2026-07-13: M7 release evidence in `66ce3ef`: pinned development tools and
  installed-wheel doctor, release-smoke, and MCP outcome discovery checks.
- 2026-07-13: Completed M6 on `codex/gpt56-modernization` (`0b5ac2e`,
  `56c94d4`): application-owned workflow/outcome/packet/report paths, typed
  root façades, built-wheel compatibility, 520 passing tests, and clean reviews.
- 2026-07-13: Completed M5 on `codex/gpt56-modernization` (`f5c8610`):
  packet-bound response validation, combined-context isolation, lifecycle locks,
  strict handoffs, and truthful v2 artifact paths; 515 tests and release checks pass.
- 2026-07-12: Completed M4 on `codex/gpt56-modernization` (`75d8ac4`): v2
  outcome contract, outcome-first CLI/MCP journeys, bounded history, and
  safety claims tied to observed evidence; 496 tests and release checks pass.
- 2026-07-12: Completed M3 on `codex/gpt56-modernization` (`8705cc1`): typed
  verification service and v1 artifact renderer, minimal inherited environment,
  disposable-worktree recovery, timeout schema alignment, and 454 passing tests.
- 2026-07-12: Completed M2 on `codex/gpt56-modernization` (`3f23204`): typed
  audit contracts and use case, v1 artifact rendering, shared bounded scan
  scopes, preserved CLI/MCP projections, and route-surface regressions covered.
- 2026-07-12: Completed M1 on `codex/gpt56-modernization` (`cb12746`): strict
  review core/application contracts, fixed v1 baseline fixtures, closed-schema
  readers, and public typed compatibility adapters.
