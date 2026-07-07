# Architecture Contracts

Quality Runner can enforce repository-specific architecture boundaries as an
opt-in extension to the structural code-quality scan. The feature is
audit-and-plan only: it emits evidence-backed findings and remediation guidance
but does not edit target source files, install dependencies, or execute fixes.

## When to use it

Use architecture contracts when a repo has explicit layer boundaries that generic
structural heuristics cannot express, such as:

- UI code must not import server or domain internals.
- API routers may only delegate to services and schema modules.
- Validators and schemas must stay declarative and side-effect free.

Repos with no `[quality_runner.architecture]` section behave the same as before.
No architecture findings are emitted unless rules are explicitly configured and
`enabled = true`.

## V1 scope

Version 1 is deliberately conservative:

- **Import-boundary rules** inspect import/export/require statements in files
  matching configured source globs. Relative imports are resolved to
  repo-relative paths when possible; alias imports are matched only against the
  raw specifier.
- **Pattern-boundary rules** scan configured file globs for obvious forbidden
  regex patterns, such as `await`, `fetch(`, or `process.env.` inside schema or
  validator modules.
- Findings use category `architecture`, stable fingerprints, and the same
  code-quality scan artifact path as other structural findings.

This is heuristic, evidence-backed governance—not a full semantic architecture
checker.

## Example configuration

```toml
[quality_runner.architecture]
enabled = true

[[quality_runner.architecture.import_boundaries]]
id = "ui-no-server-imports"
sources = ["apps/web/**", "packages/ui/**"]
disallowed_imports = ["server/**", "packages/server/**", "packages/domain/**"]
allowed_imports = ["packages/domain/types/**"]
severity = "warning"
message = "UI code should not import server or domain internals directly."
risk = "Cross-layer imports couple presentation code to implementation details and make refactors unsafe."
expected = "Move access behind API/client/service boundaries or import only stable shared types."

[[quality_runner.architecture.import_boundaries]]
id = "routes-no-db-direct"
sources = ["**/api/**/route.ts", "**/routes/**", "**/routers/**"]
disallowed_imports = ["**/db/**", "**/database/**", "**/repositories/**"]
allowed_imports = []
severity = "observation"
message = "Routes should delegate persistence work instead of importing database internals directly."
risk = "Database access in route layers mixes transport, validation, authorization, and persistence concerns."
expected = "Delegate to a service/repository boundary and keep the route focused on validation, authorization, delegation, and response shaping."

[[quality_runner.architecture.pattern_boundaries]]
id = "validators-no-side-effects"
paths = ["**/schemas/**", "**/*schema*.ts", "**/*validator*.ts", "**/*validation*.ts"]
disallowed_patterns = [
  "\\bawait\\b",
  "\\bfetch\\s*\\(",
  "\\bprisma\\.",
  "\\bdb\\.",
  "\\bprocess\\.env\\.",
  "\\breadFile\\s*\\(",
  "\\bwriteFile\\s*\\("
]
severity = "warning"
message = "Validation/schema modules should not perform side-effectful business logic."
risk = "Side effects inside validation make input contracts harder to reuse, test, and reason about."
expected = "Keep validation modules declarative; move runtime work to services or route handlers."
```

## Recommended rollout

1. Start with one or two import-boundary rules for the highest-risk layer leaks.
2. Add pattern-boundary rules only for obvious validator/schema side effects.
3. Review findings in `code-quality-scan.json` and route remediation through the
   normal Quality Runner handoff flow.

See also [Standards Profiles](standards-profiles.md) for broader repo policy
configuration.
