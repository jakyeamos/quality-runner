# Standards Profiles

Quality Runner compiles a standards packet before detecting capabilities and
building audit findings.

## Built-In Profile

The current built-in profile is:

- `default`
- `release`, which adds provenance, artifact-manifest, package-consumer,
  migration, acceptance, read-only-integrity, and aggregate-coverage gates

It expects:

- pnpm for JavaScript dependency management
- lint, typecheck, tests, and dead-code checks before completion
- optional planning notes when a repository chooses to keep them
- audit-and-plan-only behavior from Quality Runner itself

The `release` profile is selected with `--profile release` or by setting
`default_profile = "release"`. It is evidence-first: local CI status and
release evidence are read from files inside the target repository, and
executable gates require explicit disposable-worktree authorization.

## Repo Policy

Repos can add `.quality-runner.toml` to make local policy explicit:

```toml
[quality_runner]
default_profile = "default"
required_capabilities = ["lint", "tests", "dead_code"]
allowed_package_managers = ["pnpm"]
scan_exclusions = ["samples", "generated-reports/**"]

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
complexity_thresholds = { python = 15, javascript = 20 }
report_unverified_complexity_reductions = false

[quality_runner.readiness]
evidence_file = ".quality-runner/release-evidence.json"

[[quality_runner.gates]]
id = "lint"
command = "make lint"
ecosystem = "make"
source = "local policy"
owner = "platform"
required = true
severity = "blocker"
mutating_risk = "unknown"

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

Configured gates are recorded as command evidence only. Quality Runner does not
execute them.

`scan_exclusions` augments the default discovery exclusions. Defaults skip
fixture corpora, generated corpora, docs, vendored directories, and third-party
trees so embedded examples do not appear as first-class workspaces in self-audit
artifacts.

Structural scan findings are default-on and non-blocking. Repos can disable
rule groups, tune large-file/router thresholds, or preserve accepted dispositions
by stable finding fingerprint.

The `simplify` group measures cyclomatic complexity per Python and
JavaScript/TypeScript function. The default advisory thresholds are 15 for
Python and 20 for JavaScript; repositories can tune them by language with
`complexity_thresholds`. Code-quality artifacts include the function symbol,
score, threshold, and counted decision types so a reviewer can inspect the
measurement. Task baselines compare changed functions with a matching
file-and-symbol metric and report increases as `complexity-regression`
observations, even when the function remains below its advisory threshold.
`report_unverified_complexity_reductions = true` additionally reports a large
reduction when no changed test file is present, but this is opt-in and remains
an observation. Complexity is a review signal, not proof of behavioral
correctness; Quality Runner does not require mutation testing, and any mutation
results remain optional external evidence.

Opt-in architecture contracts add repo-specific import-boundary and
pattern-boundary rules under `[quality_runner.architecture]`. See
[Architecture Contracts](architecture-contracts.md) for configuration examples and
rollout guidance.

Unknown profiles fail closed unless they are defined under
`quality_runner.profiles`.

`failure_visibility` is an opt-in capability rather than a built-in default.
Require it for repositories where fallback, degradation, or evidence ingestion
can make failed work look successful or absent. Its gate must exercise negative
paths and validate machine-readable consumer readback; see
[Failure Visibility Capability](failure-visibility.md).

CLI examples omit `--profile` because `default` is selected automatically unless
a repo config sets a different default. `--profile <name>` can select either the
built-in `default` profile or a custom profile saved in `.quality-runner.toml`.
