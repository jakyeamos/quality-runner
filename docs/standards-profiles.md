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

## Repo Policy

Repos can add `.quality-runner.toml` to make local policy explicit:

```toml
[quality_runner]
default_profile = "jakyeamos"
required_capabilities = ["lint", "tests", "dead_code"]
allowed_package_managers = ["pnpm"]

[quality_runner.severity_overrides]
missing-dead-code = "warning"

[[quality_runner.gates]]
id = "lint"
command = "make lint"
ecosystem = "make"
source = "local policy"
owner = "platform"
required = true
severity = "blocker"

[[quality_runner.accepted_exceptions]]
capability = "dead_code"
reason = "Legacy repo is being migrated in phases."
owner = "platform"
expires = "2026-12-31"
```

Configured gates are recorded as command evidence only. Quality Runner does not
execute them.

Unknown profiles fail closed.
