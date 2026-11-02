# Coding and artifact conventions

Last reviewed: 2026-11-02

- Target Python 3.12 or newer and preserve the locked `uv` environment.
- Add explicit public return types and typed boundaries for new production
  code. Fix real type errors; do not add broad ignores or casts that hide them.
- Preserve the full-package standard and strict BasedPyright checks. Strict
  diagnostics must remain at zero, with the pinned baseline ratchet enforced
  in CI. Narrow untyped input only after validating its runtime container;
  keep field values checked instead of asserting an unverified domain type.
- Keep CLI, MCP, artifact, and schema contracts deterministic. Sort emitted
  collections where order is not semantically meaningful.
- Preserve evidence provenance, run IDs, schema versions, and redaction
  metadata when transforming artifacts. Never invent missing gate results.
- Keep target-repository writes under `.quality-runner/runs/<run-id>/` and make
  execution mode explicit in every result.
- Prefer behavior-focused tests for public commands, workflow contracts,
  artifact schemas, safety boundaries, and confirmed regressions.
- Keep compatibility aliases working until their documented removal condition
  is reached. Update the CLI and artifact documentation with contract changes.
