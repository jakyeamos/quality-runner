# Good implementation examples

last_reviewed: 2026-07-22

Use existing implementations as the local pattern before adding a new helper.

- `quality_runner/application/read_only_audit.py` keeps audit orchestration
  separate from source mutation.
- `quality_runner/application/outcome_projection.py` exposes bounded, truthful
  outcomes without hiding unresolved evidence.
- `quality_runner/evidence_redaction.py` and
  `quality_runner/evidence_redaction_contract.py` centralize sensitive-evidence
  handling before persistence.
- `quality_runner/core/` contains typed contracts that are shared deliberately.
- `docs/examples/developer-experience.toml` shows the local Quality Skill
  format and review boundaries.

Compare a proposed change with these patterns and the relevant tests before
creating a parallel abstraction. The [architecture examples](../../docs/examples/architecture-maintainability.toml)
and [skill documentation](../../docs/quality-skills.md) show the supported
configuration shape.
