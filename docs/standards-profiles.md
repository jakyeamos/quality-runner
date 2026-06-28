# Standards Profiles

Quality Runner compiles a standards packet before detecting capabilities and
building audit findings.

## Built-In Profile

The current built-in profile is:

- `jakyeamos`

It expects:

- pnpm for JavaScript dependency management
- lint, typecheck, tests, and dead-code checks before completion
- `.tracker/PROJECT_TRUTH.md` maintenance when a repo has a truth file
- audit-and-plan-only behavior from Quality Runner itself

## Profile Boundary

Profile support is intentionally narrow in v0.1. A future
`.quality-runner.toml` config file should make profiles, required gates, and
accepted exceptions explicit per repository.

Until that config exists, unknown profiles fail closed.
