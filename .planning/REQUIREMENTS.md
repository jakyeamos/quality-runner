# Requirements: quality-runner

**Defined:** 2026-07-04
**Core Value:** Keep quality-runner healthy by resolving Quality Runner findings with behavior-preserving, evidence-backed remediation.

## v1 Requirements

### QR Remediation

- [ ] **QR-QUALITY-RUNNER**: Resolve the Quality Runner advisory clusters from run qr-fleet-continue-20260704-quality-runner for quality-runner without changing intended behavior, then verify with focused repo checks and a post-remediation QR comparison.

### Fresh Review

- [x] **FR-FRESH-CONTEXT**: Every task, blind, or combined review starts from a newly constructed context packet without inherited implementation-agent reasoning or active-cycle review reports.
- [x] **FR-REVIEW-MODES**: Users can run task-aware adversarial, fully blind, and combined reviews with task/project scope, focused/related/full breadth, exclusions, and evidence limitations represented in the result.
- [x] **FR-REPORTS**: Each review produces a saved human-readable and machine-readable report with ranked severity, classification, confidence, evidence, uncertainty, suggested fixes, and separate fixing-agent prompts.
- [x] **FR-STATE**: The workflow stores known issues and tracks finding resolution locally while deferring cross-report matching until the end of an implement-review cycle.
- [x] **FR-BYO-AGENT**: The workflow can hand a fresh packet to a user-selected agent or file-based adapter and reports unavailable capabilities without fabricating review results.
- [x] **FR-SAFETY**: The reviewer remains local-first and read-only, never editing source files, installing dependencies, committing, or executing remediation.

## v2 Requirements

### Fleet Quality

- **QR-FLEET-BASELINE**: Keep this repo in the recurring QR fleet once the initial remediation phase closes.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Broad rewrite | QR remediation should stay clustered and behavior-preserving. |
| QR execution | Quality Runner is advisory-only. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| QR-QUALITY-RUNNER | Phase 1 | Pending |
| FR-FRESH-CONTEXT | Phase 2 | Complete |
| FR-REVIEW-MODES | Phase 2 | Complete |
| FR-REPORTS | Phase 2 | Complete |
| FR-STATE | Phase 2 | Complete |
| FR-BYO-AGENT | Phase 2 | Complete |
| FR-SAFETY | Phase 2 | Complete |

**Coverage:**
- v1 requirements: 7 total
- Mapped to phases: 2
- Unmapped: 0

---
*Requirements defined: 2026-07-04*
*Last updated: 2026-07-04 after QR remediation GSD bootstrap*
