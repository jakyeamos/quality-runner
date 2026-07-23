# Coding and compatibility conventions

last_reviewed: 2026-07-22

- Target Python 3.12+ and keep the Ruff line length at 100.
- Keep public JSON schemas, CLI projections, MCP contracts, and compatibility
  packages stable unless the change includes an explicit migration path.
- Prefer typed application services over adding behavior to CLI or MCP adapters.
- Keep read-only discovery separate from commands that execute gates.
- Preserve redaction and provenance before storing source-derived evidence.
- Add a regression test for contract, artifact, boundary, or safety behavior;
  avoid tests that only restate a static presentation detail.
- Keep generated artifacts and caches out of source changes unless the artifact
  is intentionally versioned and its provenance is recorded.

See [CONTRIBUTING.md](../../CONTRIBUTING.md) and the
[architecture guide](../../docs/architecture-contracts.md) before changing
shared types or package ownership.
