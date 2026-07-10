# Modernization Progress

## Current state

Audit and target design are complete at baseline commit `0a3def1` on the
protected branch `codex/gpt56-modernization`. No application code has changed.
The next action is approval to begin M0 from [EXEC_PLAN.md](EXEC_PLAN.md).

## Decisions in force

- Use a parallel typed core with controlled adapters, not a clean rewrite.
- Treat the CLI/MCP workflow as the primary interface; do not build a web UI as
  part of this modernization.
- Preserve public artifact and compatibility contracts while making execution
  safer by default.

## Baseline quality

- Package build and Vulture passed.
- Tests, lint, formatting, and type checking exposed pre-existing failures; the
  audit records their causes and remediation order in [AUDIT.md](AUDIT.md).
- Release smoke passed but does not yet protect against version-contract drift.

## Next milestone

M0 restores trust at the public and security boundary before the v2 core is
introduced. Its completion gate is a passing release-contract suite plus
path-traversal, symlink, and execution-policy regression coverage.
