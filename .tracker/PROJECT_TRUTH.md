# Quality Runner Project Truth

Last updated: 2026-07-12

## Current State

Quality Runner is a public, local-first quality orchestration package. It
inspects repositories, records evidence, plans remediation, and hands execution
to separately authorized humans or agents. It does not own autonomous source
changes or remote review execution.

`main` is the 0.5.0 release baseline. The protected
`codex/gpt56-modernization` branch contains M0 trust-boundary work in
`f36dcf4`, M1 typed Fresh Review contracts in `cb12746`, and M2 typed
read-only audit orchestration in `3f23204`, producing an unreleased 0.5.1
candidate. No tag or package publication has occurred.

## Current Position

- Target: a typed v2 core behind CLI, MCP, and compatibility adapters.
- Next implementation slice: M3 — migrate verification through its own
  policy-controlled application boundary.
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

- The full pytest suite, Ruff lint/format, Basedpyright, Vulture, package build,
  and release smoke pass.
- Basedpyright reports zero errors; Fresh Review now uses strict core contracts
  behind v1 JSON and Python compatibility projections.
- Release smoke now checks package/runtime/plugin parity and the release
  workflow enforces tag, wheel, manifest, and citation contracts.

## Risks

- M3 must preserve verification evidence, explicit execution consent, and
  worktree safety while moving gate execution through one typed use case.
- Existing large-file warnings remain in `repo_quality_certifier/core.py` and
  `tests/test_cli.py`.
- User-authored gate commands remain arbitrary code; M0 requires explicit
  consent and a disposable checkout but does not sandbox those commands.
- Combined file-adapter task provenance remains the baseline-compatible string
  `"None"`; M5 owns a behavior redesign after the compatibility window.

## Recent Progress

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
