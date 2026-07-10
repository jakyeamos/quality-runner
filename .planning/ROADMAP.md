# Roadmap: quality-runner QR Remediation

**Created:** 2026-07-04
**Mode:** quality-remediation
**Plan Format:** GSD numbered executable plans generated from Quality Runner per-repo summaries.

### Phase 1: QR remediation: quality-runner


**Goal:** Resolve Quality Runner findings for quality-runner using cluster-oriented, behavior-preserving remediation from run qr-fleet-continue-20260704-quality-runner.
**Requirements**: QR-QUALITY-RUNNER
**Depends on:** Phase 0
**Plans:** 1 plans

Plans:
- [ ] 01-01-PLAN.md - Primary QR cluster remediation

### Phase 2: Fresh Review

**Goal:** Deliver the local-first Fresh Review workflow described in `docs/fresh-review-prd.md`, including fresh task/blind/combined review context, saved reports, known-issue and resolution state, and separate agent handoff without source mutation.
**Requirements**: FR-FRESH-CONTEXT, FR-REVIEW-MODES, FR-REPORTS, FR-STATE, FR-BYO-AGENT, FR-SAFETY
**Depends on:** Phase 1
**Plans:** 5 plans

Plans:
**Wave 1**
- [x] 02-01-PLAN.md - Define review contracts and fresh task/blind/combined context packets

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 02-02-PLAN.md - Normalize reports and persist Markdown/JSON/fix-prompt artifacts

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 02-03-PLAN.md - Add file/BYO adapter boundary and review CLI command

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 02-04-PLAN.md - Add known issues, resolution state, and implement-review loop

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 02-05-PLAN.md - Expose MCP review tool and document the workflow

---
*Last updated: 2026-07-04 after QR remediation GSD bootstrap*
