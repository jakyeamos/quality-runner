# CLI Reference

Quality Runner provides two console scripts:

- `quality-runner`
- `quality-runner-mcp`

## `quality-runner doctor`

Checks local install readiness.

```bash
quality-runner doctor --json
```

Returns:

- schema: `quality-runner-doctor-result-v0.1`
- status: `ready`
- package version
- local Python/platform details

## `quality-runner inspect`

Inspects repo shape, standards, and quality capability signals without producing
audit or remediation artifacts.

```bash
quality-runner inspect /path/to/repo --run-id inspect-001 --json
quality-runner inspect /path/to/repo --ci-status-json ci-status.json --json
quality-runner inspect /path/to/repo --checkout-most-advanced-branch --json
```

The standards profile defaults to `default`; use `--profile` only to select a
saved custom profile or override repo config.

By default, scans use the branch that is already checked out. If that branch is
neither `main` nor the local branch with the highest commit count, the repo scan
includes a warning. Use `--checkout-most-advanced-branch` to switch to that
local most-advanced branch before scanning; this requires a clean worktree.

Writes:

- `repo-scan.json`
- `code-quality-scan.json`
- `package-manager-preflight.json`
- `standards.json`
- `capability-matrix.json`

## `quality-runner init`

Writes a starter `.quality-runner.toml`.

```bash
quality-runner init /path/to/repo \
  --required-capability lint \
  --required-capability tests \
  --json
```

Use `--force` to replace an existing config.

The same config file can add repo-specific scan exclusions:

```toml
[quality_runner]
scan_exclusions = ["samples", "generated-reports/**"]
```

These augment the default exclusions for fixtures, corpora, docs, vendored
trees, and tool output directories.

## `quality-runner status`

Reports the normalized repo config and latest run metadata.

```bash
quality-runner status /path/to/repo --json
```

## `quality-runner run`

Runs the full audit-and-plan workflow.

```bash
quality-runner run /path/to/repo --run-id baseline-001 --json
quality-runner run /path/to/repo --ci-status-json ci-status.json --json
quality-runner run /path/to/repo --checkout-most-advanced-branch --json
```

The standards profile defaults to `default`; use `--profile` only to select a
saved custom profile or override repo config.

By default, scans use the branch that is already checked out. If that branch is
neither `main` nor the local branch with the highest commit count, the repo scan
includes a warning. Use `--checkout-most-advanced-branch` to switch to that
local most-advanced branch before scanning; this requires a clean worktree.

Writes:

- `repo-scan.json`
- `code-quality-scan.json`
- `package-manager-preflight.json`
- `standards.json`
- `capability-matrix.json`
- `quality-audit.json`
- `remediation-plan.json`
- `resolution-ledger.json`
- `resolution-ledger.md`
- `agent-handoff.json`
- `agent-handoff.md`

## `quality-runner verify-gates`

Executes discovered command-backed repo gates and records local pass/fail
evidence without applying remediation. JavaScript package scripts execute
through the detected package manager, and CI-only gates without a local executor
are reported as skipped. File/evidence capabilities such as a truth file are
kept in the capability matrix but do not block executable gate verification.

```bash
quality-runner verify-gates /path/to/repo --run-id verify-001 --json
quality-runner verify-gates /path/to/repo --timeout-seconds 300 --json
```

Repos can override individual gate timeouts in `.quality-runner.toml`:

```toml
[quality_runner.gate_timeouts]
tests = 300
pre_cr = 600
```

Possible verification statuses include `passed`, `passed-with-findings`,
`failed`, `blocked`, and `skipped-nonlocal`.

Writes:

- `repo-scan.json`
- `code-quality-scan.json`
- `package-manager-preflight.json`
- `standards.json`
- `capability-matrix.json`
- `gate-verification.json`
- `quality-audit.json`
- `remediation-plan.json`
- `agent-handoff.json`
- `agent-handoff.md`
- `run-manifest.json`

## `quality-runner refresh`

Runs `inspect`, `run`, read-only `verify-gates`, and `summarize-run` as one
controller-friendly workflow.

```bash
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --json
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --verify-timeout-seconds 300 --json
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --total-timeout-seconds 900 --json
```

Timeout flags are explicit about scope:

- `--timeout-seconds` caps each individual gate command.
- `--verify-timeout-seconds` caps the `verify-gates` phase.
- `--workflow-timeout-seconds` is a backward-compatible alias for
  `--verify-timeout-seconds`.
- `--total-timeout-seconds` is optional and caps the full refresh across
  inspect, run, and verify.
- `--workflow-timeout-reason` records why the verify-phase deadline exists.
- `--total-timeout-reason` records why the full refresh deadline exists.

Refresh JSON includes `timeout_contract` and `phase_timings` so controllers can
distinguish a deliberate full-evidence run from a hard end-to-end deadline.
When a timeout fires, `workflow-timeout.json`, the verify result, and
`gate-verification.json` include `timeout_scope` as either `verify-phase` or
`total-refresh`.

Agent handoffs from refresh use `quality-runner-agent-handoff-v0.2` and route
verified gate outcomes with `gates-clean`, `gates-blocked`, and `gates-failed`.
Blocked and failed handoffs include `gate_verification.blocker_groups` and
`next_slice.action_groups` so controllers can distinguish dependency setup,
environment restrictions, read-only policy blockers, and executable gate
failures before launching the next worker.

If inspect, run, or verify times out before normal verification completes,
refresh still writes a final `agent-handoff.json`/`.md` with a
`workflow-timeout` blocker group. `workflow-timeout.json` also includes scan
progress diagnostics with the last traversal directory, recent paths, visited
path count, and skipped path count.

## `quality-runner validate-report`

Validates a controller thread completion report before the controller advances a
wave.

```bash
quality-runner validate-report worker-report.json --json
```

Completed reports must have a clean `git_status_short`, a `commit_hash`, and
`push_status` set to `pushed`. Generated artifacts such as `.quality-runner/`
can be listed under `ignored_generated_artifacts` when they are the only dirty
paths. Blocked reports must include explicit blockers.

Worker threads should run this as their final self-check before reporting back
to a controller. The command is intentionally strict and does not normalize
repo-specific report shapes.

## `quality-runner controller-report`

Normalizes or lints controller thread reports.

```bash
quality-runner controller-report normalize worker-report.json --json
quality-runner controller-report normalize worker-report.json --output normalized-report.json
quality-runner controller-report lint worker-report.json --strict --json
```

`normalize` accepts common nested worker report shapes and emits the strict
`quality-runner-controller-report-v0.1` shape expected by `validate-report`.
`lint --strict` also enforces controller semantics: `complete` requires a clean
final QR result plus commit/push evidence, and reports that observe target HEAD
changes must include an explicit concurrency note.

## `quality-runner summarize-run`

Prints a controller-friendly run summary with final status, gate table, missing
capabilities, finding counts, a recommended classification, and an optional
baseline delta.

```bash
quality-runner summarize-run /path/to/repo --run-id final-001 --json
quality-runner summarize-run /path/to/repo --run-id final-001 --baseline-run-id baseline-001 --json
quality-runner summarize-run /path/to/repo --run-id final-001 --baseline-run-id baseline-001 --controller-report --branch-name qr/example --json
```

With `--controller-report`, the command emits a strict controller-report
skeleton using the run summary, current git status, branch name, baseline path,
and inferred blockers. Workers can add explicit `--blocker`, `--file-changed`,
`--commit-hash`, `--push-status`, and `--thread-status` values before running
`quality-runner validate-report`.

## `quality-runner export-handoff`

Prints the latest `agent-handoff.md`, or a selected run handoff.

```bash
quality-runner export-handoff /path/to/repo
quality-runner export-handoff /path/to/repo --run-id baseline-001 --output handoff.md --json
```

## Exit Behavior

- `0`: command completed successfully.
- `1`: validation or filesystem error.
- `2`: argument parsing error.

Errors are printed to stderr without Python tracebacks.
