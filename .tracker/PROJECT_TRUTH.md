# Quality Runner Project Truth

Last updated: 2026-07-10

## Current State

Quality Runner is a public, local-first quality orchestration package. It
inspects repositories, records evidence, plans remediation, and hands execution
to separately authorized humans or agents. It does not own autonomous source
changes or remote review execution.

`main` is the 0.5.0 release baseline. The protected
`codex/gpt56-modernization` branch contains the approved-for-review
modernization audit and plan; no application implementation has started there.

## Current Position

- Target: a typed v2 core behind CLI, MCP, and compatibility adapters.
- First implementation slice: M0 — restore release, artifact-boundary, and
  verification-policy trust.
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

- Package build and Vulture pass at the release baseline.
- The full test suite exposes one release-version contract failure.
- Lint, format, and type checks expose pre-existing Fresh Review and import-order
  debt.
- Release smoke currently passes without testing package/runtime/plugin version
  parity; M0 closes that gap.

## Risks

- Artifact path traversal and symlink safety are inconsistent across public
  entry points.
- Untrusted repository gate commands can currently execute under a misleading
  read-only label.
- Public release metadata is internally inconsistent.

## Recent Progress

- 2026-07-10: Added the modernization audit, target, execution plan, and live
  progress record on `codex/gpt56-modernization` (commit `a40a811`).
