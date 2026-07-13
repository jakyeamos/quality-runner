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
direct-combined compatibility contracts. M7 release hardening is next.

## Current Position

- Target: a typed v2 core behind CLI, MCP, and compatibility adapters.
- Next implementation slice: M7 — make release, cutover, rollback, and
  operational evidence reproducible from the built distribution.
- Canonical planning documents: `docs/modernization/`.
- Public compatibility: retain `quality_evidence_contract` and
  `repo_quality_certifier` during a published transition window.

## Core Contract

- Local-first operation with no silent remote transfer.
- Auditing/planning stays separate from source mutation.
- JSON artifacts remain canonical; Markdown remains the human decision surface.
- Scan-only and code-executing verification are explicit, separately reported
  modes.

## Baseline Quality

- The full 520-test pytest suite, Ruff lint/format, Basedpyright, Vulture,
  package build, and release smoke pass.
- Basedpyright reports zero errors; audit, review, verify, and run history now
  have a versioned v2 outcome contract behind preserved v1 projections.
- Release smoke now checks package/runtime/plugin parity and the release
  workflow enforces tag, wheel, manifest, and citation contracts.

## Risks

- M7 must keep public v1 readers and rollback guidance accurate while any v2
  default or deprecation policy is documented.
- Existing large-file warnings remain in `repo_quality_certifier/core.py` and
  `tests/test_cli.py`.
- User-authored gate commands remain arbitrary code; M0 requires explicit
  consent and a disposable checkout but does not sandbox those commands.
- Combined file-adapter task provenance remains the baseline-compatible string
  `"None"` until a published compatibility cutover can change that projection.

## Recent Progress

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
- 2026-07-12: Completed M0 on `codex/gpt56-modernization` (`f36dcf4`), including
  safe artifact paths, explicit gate execution policy, release-contract checks,
  truthful Fresh Review output, and hook-environment isolation.
- 2026-07-10: Added the modernization audit, target, execution plan, and live
  progress record (`a40a811`).
