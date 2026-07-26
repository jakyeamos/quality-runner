# Coding and artifact conventions

- Target Python 3.12 or newer and preserve the locked `uv` environment.
- Add explicit public return types and typed boundaries for new production
  code. Fix real type errors; do not add broad ignores or casts that hide them.
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
