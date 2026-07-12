# Quality Runner Project Truth

Last updated: 2026-07-12

## Current State

Quality Runner is a public, local-first quality orchestration package. It
inspects repositories, records evidence, plans remediation, and hands execution
to separately authorized humans or agents. It does not own autonomous source
changes or remote review execution.

`main` is the 0.5.0 release baseline. The protected
`codex/gpt56-modernization` branch contains the completed M0 trust-boundary
implementation in `f36dcf4`, producing an unreleased 0.5.1 candidate. No tag
or package publication has occurred.

## Current Position

- Target: a typed v2 core behind CLI, MCP, and compatibility adapters.
- Next implementation slice: M1 — establish typed v2 contracts and remove the
  Fresh Review type debt.
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

- `uv run --offline pytest -q` passes: 410 tests.
- Ruff, formatting, Vulture, package build, and release smoke pass.
- basedpyright has 14 pre-existing Fresh Review TypedDict errors, explicitly
  deferred to M1; M0 introduces none.
- Release smoke now checks package/runtime/plugin parity and the release
  workflow enforces tag, wheel, manifest, and citation contracts.

## Risks

- M1 must resolve the 14 Fresh Review typed-contract errors.
- Existing large-file warnings remain in `repo_quality_certifier/core.py` and
  `tests/test_cli.py`.
- User-authored gate commands remain arbitrary code; M0 requires explicit
  consent and a disposable checkout but does not sandbox those commands.

## Recent Progress

- 2026-07-12: Completed M0 on `codex/gpt56-modernization` (`f36dcf4`), including
  safe artifact paths, explicit gate execution policy, release-contract checks,
  truthful Fresh Review output, and hook-environment isolation.
- 2026-07-10: Added the modernization audit, target, execution plan, and live
  progress record (`a40a811`).
