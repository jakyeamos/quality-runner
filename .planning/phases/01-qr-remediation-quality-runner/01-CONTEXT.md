# Phase 1: QR remediation: quality-runner - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning
**Source:** PRD Express Path (/Users/jakyeamos/.local/state/quality-runner/fleet/per-repo-summaries-20260704/quality-runner.md)

<domain>
## Phase Boundary

Plan the remediation work for quality-runner from Quality Runner run qr-fleet-continue-20260704-quality-runner.
This phase is planning-only until execute-phase runs. Quality Runner remains advisory-only: it identifies findings, remediation clusters, and verification suggestions, but all source changes happen in /Users/jakyeamos/projects/quality-runner.

Findings: 1
Severity: `warning` 1
Categories: `structural:simplify` 1
Fleet phase candidate: Phase 0 - Control Plane And Branch Hygiene
Requirement: QR-QUALITY-RUNNER

</domain>

<decisions>
## Implementation Decisions

### D-01 - QR summary is the planning source
- Use /Users/jakyeamos/.local/state/quality-runner/fleet/per-repo-summaries-20260704/quality-runner.md and the artifacts under /Users/jakyeamos/projects/quality-runner/.quality-runner/runs/qr-fleet-continue-20260704-quality-runner as the source of truth for this remediation phase.

### D-02 - Cluster-oriented remediation
- Plan and execute coherent remediation batches by QR cluster, not one isolated edit per finding row.

### D-03 - Behavior preservation
- Prefer behavior-preserving refactors, hardening, and simplification. Do not change product behavior unless a QR hardening cluster explicitly requires safer behavior.

### D-04 - Existing project conventions first
- Read the target files and local manifests before editing. Follow existing package-manager, formatter, test, and architecture conventions. Use pnpm for JavaScript package scripts.

### D-05 - Evidence-backed closure
- A cluster is done only when focused repo verification passes and a post-remediation QR run shows the fingerprints cleared or are dispositioned with evidence.

### Claude's Discretion
- Choose exact helper extraction boundaries, naming, and task order when the QR document identifies the finding but not the implementation shape.
- If a cluster turns out to require product, API, or design decisions, stop that cluster and capture the question instead of guessing.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Quality Runner Inputs
- `/Users/jakyeamos/.local/state/quality-runner/fleet/per-repo-summaries-20260704/quality-runner.md` - Per-repo QR summary used as this phase PRD.
- `/Users/jakyeamos/projects/quality-runner/.quality-runner/runs/qr-fleet-continue-20260704-quality-runner/quality-audit.json` - Quality audit report.
- `/Users/jakyeamos/projects/quality-runner/.quality-runner/runs/qr-fleet-continue-20260704-quality-runner/remediation-plan.json` - QR remediation plan.
- `/Users/jakyeamos/projects/quality-runner/.quality-runner/runs/qr-fleet-continue-20260704-quality-runner/code-quality-scan.json` - Code-quality scan fingerprints.
- `/Users/jakyeamos/projects/quality-runner/.quality-runner/runs/qr-fleet-continue-20260704-quality-runner/resolution-ledger.md` - Resolution ledger for closure evidence.
- `/Users/jakyeamos/projects/quality-runner/.quality-runner/runs/qr-fleet-continue-20260704-quality-runner/agent-handoff.md` - QR agent handoff.

</canonical_refs>

<specifics>
## Top Findings

- `structural-simplify-large-source-file` warning structural:simplify: 1 large-source-file structural finding in simplification and shrink pass. Fix: 1 findings, aggregate score 9: Split mixed responsibilities into focused modules. Evidence: repo_quality_certifier/core.py:1: large-source-file

## Remediation Clusters

1. remediate-structural-repo-quality-certifier-core-py (medium, score 9) - Remediate structural cluster in repo_quality_certifier/core.py

</specifics>

<deferred>
## Deferred Ideas

- Broad rewrites outside the QR clusters.
- Running Quality Runner as an executor or letting QR mutate source code.
- Remediating repos outside quality-runner; each repo gets its own GSD phase.

</deferred>

---

*Phase: 1*
*Context gathered: 2026-07-04 via QR per-repo PRD*
