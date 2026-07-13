# Standards Profiles

Quality Runner compiles a standards packet before detecting capabilities and
building audit findings.

## Built-In Profile

The current built-in profile is:

- `default`

It expects:

- pnpm for JavaScript dependency management
- lint, typecheck, tests, and dead-code checks before completion
- `.tracker/PROJECT_TRUTH.md` maintenance when a repo has a truth file
- audit-and-plan-only behavior from Quality Runner itself

## Repo Policy

Repos can add `.quality-runner.toml` to make local policy explicit:

```toml
[quality_runner]
default_profile = "default"
required_capabilities = ["lint", "tests", "dead_code"]
allowed_package_managers = ["pnpm"]
scan_exclusions = ["samples", "generated-reports/**"]

[quality_runner.artifacts]
redact_patterns = ["(?i)\\b(?:api[_-]?(?:key|token)|password)\\b\\s*[:=]\\s*[^\\s,;]+"]
redact_replacement = "[REDACTED]"
retention_runs = 30
retention_days = 30

[quality_runner.severity_overrides]
missing-dead-code = "warning"

[quality_runner.structural_scan]
disabled_rule_groups = ["ui_structural"]
large_file_lines = 900
fat_router_lines = 400
similarity_enabled = true
similarity_threshold = 0.9
similarity_min_lines = 10
similarity_max_pairs = 20

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

[[quality_runner.accepted_dispositions]]
fingerprint = "abc123"
status = "accepted-intentional"
reason = "The large test file is one cohesive math invariant suite."
owner = "qa"
expires = "2026-12-31"
source_run_id = "qr-20260707-run"
review_evidence = ["code-quality-scan.json:CQ-0012"]
```

Optional `source_run_id` and `review_evidence` tie accepted dispositions back
to the QR run and artifact rows that justified the decision. These fields feed
`resolution-ledger.json` and help workers distinguish intentional tradeoffs from
stale findings.

Repos can also save named custom profiles and select them as the default:

```toml
[quality_runner]
default_profile = "team"

[quality_runner.profiles.team]
extends = "default"
required_capabilities = ["lint", "typecheck", "tests", "dead_code"]
allowed_package_managers = ["pnpm", "bun"]
```

Custom profiles are repository-local. They must currently extend `default`.
Profile-level `required_capabilities` and `allowed_package_managers` provide
saved defaults; top-level repo policy can still override them.

Configured gates are recorded as command evidence during `inspect` and `run`.
`verify-gates` is the explicit command that executes discovered gates.

Artifact policy is applied to files under `.quality-runner/runs/`. Each configured
`redact_patterns` entry is a regular expression applied before JSON or Markdown
content is written. The pattern text is not emitted into artifacts. Retention is
an explicit cleanup policy: `retention_runs` keeps the newest runs and
`retention_days` removes runs older than the configured age. Preview or apply it
with `quality-runner prune-artifacts <repo-path> [--apply]`; the default is a
dry run. When both retention limits are set, either limit can select a run for
deletion. Symlinked run directories are skipped.

For Python repositories managed by `uv`, a dependency audit is an executable
gate rather than a claim inferred from `pyproject.toml` or `uv.lock`:

```toml
[[quality_runner.gates]]
id = "security_dependency_audit"
command = "uv export --frozen --format requirements.txt --no-dev --no-emit-project | uv run --with pip-audit pip-audit -r /dev/stdin --strict --disable-pip --no-deps"
ecosystem = "python"
source = "repository security policy"
owner = "platform"
required = true
severity = "blocker"
```

`verify-gates` executes this command when it is available, so the artifact
records discovery and pass/fail evidence separately.

`scan_exclusions` augments the default discovery exclusions. Defaults skip
fixture corpora, generated corpora, docs, vendored directories, and third-party
trees so embedded examples do not appear as first-class workspaces in self-audit
artifacts.

Structural scan findings are default-on and non-blocking. Repos can disable
rule groups, tune large-file/router thresholds, or preserve accepted dispositions
by stable finding fingerprint.

Opt-in architecture contracts add repo-specific import-boundary and
pattern-boundary rules under `[quality_runner.architecture]`. See
[Architecture Contracts](architecture-contracts.md) for configuration examples and
rollout guidance.

Unknown profiles fail closed unless they are defined under
`quality_runner.profiles`.

CLI examples omit `--profile` because `default` is selected automatically unless
a repo config sets a different default. `--profile <name>` can select either the
built-in `default` profile or a custom profile saved in `.quality-runner.toml`.
