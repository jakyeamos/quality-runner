# Subsystem bootstrap

Source baseline: `1913ec18131bc868c53f20f29d0973f740dbb06a` on `dev`, inspected 2026-09-08.

This repository decides whether development evidence is current and usable. Existing draft boundaries need exact source bindings, task-baseline ownership, and conservative consumer handoffs.

- **audit-evidence-engine**: Inspect bounded repository inputs and normalize explainable audit evidence without performing remediation. 8 observed paths; draft ownership. Sources: `.agents/context/architecture.md`, `docs/integration-boundaries.md`.

- **review-handoff-output**: Turn audit evidence into review and remediation handoffs while preserving uncertainty and execution ownership. 4 observed paths; draft ownership. Sources: `docs/integration-boundaries.md`, `docs/artifacts.md`.

- **consumer-contracts**: Expose versioned evidence to Pronto and other consumers without inventing readiness or downstream proof. 10 observed paths; draft ownership. Sources: `docs/integrations/pronto-maturity-feed.md`, `docs/integration-boundaries.md`, `.pronto/behavior-assurance.json`.

- **task-verification**: Compare a task with its immutable baseline and require exact-current evidence before release eligibility. 10 observed paths; draft ownership. Sources: `docs/prevention-readiness.md`, `docs/cli.md`.

## Authority and evidence

Existing root intent and prior quiz sessions are preserved. Every new or refined subsystem remains draft; path bindings and decision records are proposed. Code supplies observed structure, and linked specifications supply documented constraints. This bootstrap neither ratifies ownership nor authorizes implementation, release, scheduling, or new blocking gates.

`development.json` enumerates exact observed paths against a broader source inventory. Proposed paths do not count as accepted coverage. Unmapped paths remain visible. Required commands are existing regression checks; they are not represented as current proof or sufficient admission evidence.

The source baseline is committed dev; concurrent task-feedback and Mac Control edits in the primary checkout are excluded and require reconciliation after integration. Declared proof covers local contracts; downstream Pronto UI and hosted release proof remain separate. Unmapped Python modules and behavior IDs remain visible.

## Focused reconciliation

The evidence digest above supplies the candidates for session `subsystem-bootstrap-20260908` in `quiz.json`. Prior unanswered sessions remain preserved. No answers were inferred.

1. I retained audit collection, review handoff, and consumer contracts, and propose a separate task-verification boundary for baseline lineage and release eligibility. Should task verification stand alone or remain inside audit collection?

2. The feed contract already separates coherent publication from quality readiness. Is the proposed split correct: QR owns identity/freshness and evidence meaning, while each consumer owns presentation and live readback?

## Maintenance

Use the installed Project Compass helper to read `family` and request `change-context` for exact task paths in the selected workspace. Follow its returned canonical references, neighboring constraints, and proof requirements. Reconcile ownership before promoting draft intent. Recompute after the actual diff; a rename or new path needs an explicit mapping, and changed shared inputs require consumer reassessment.

The bootstrap changes metadata and orientation only. It adds no application behavior, dependency, release gate, or runtime distribution change. The change-surface matrix records Compass closure for future add/change/remove/fold operations.
