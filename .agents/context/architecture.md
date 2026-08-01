# Architecture and boundaries

last_reviewed: 2026-07-22

Quality Runner is a read-only audit, evidence, planning, and handoff tool. It
does not own source remediation or remote review execution.

- `quality_runner/` owns the CLI, audit workflows, artifacts, gates, skills,
  review packets, and outcome projections.
- `quality_evidence_contract/` owns evidence schema and verification contracts.
- `repo_quality_certifier/` is a compatibility-facing certification surface.
- `tests/` owns behavioral and contract regression coverage.
- `fixtures/` owns bounded test repositories and must not be treated as live
  customer projects.
- `.quality-runner/` contains generated local runs and caches; it is not source.
- `.tracker/PROJECT_TRUTH.md` is the live project snapshot, not a changelog.

Read [architecture contracts](../../docs/architecture-contracts.md) and
[integration boundaries](../../docs/integration-boundaries.md) before changing
cross-package contracts or compatibility exports.
