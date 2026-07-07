# CLI Reference

Quality Runner provides two primary console scripts:

- `quality-runner`
- `quality-runner-mcp`

It also packages compatibility console scripts for existing Repo Quality
Certifier callers:

- `repo-quality-certifier`
- `repo-quality-certifier-mcp`

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

Unwired-work checks can also be configured. They run as structural category
`integrate` and produce decision-based remediation slices; see
[Unwired Work Detection](unwired-work.md).

## Shared Workflow Flags

`inspect`, `run`, `verify-gates`, and `refresh` share these arguments:

- `--intent`: short author goal for the run (what the user set out to accomplish)
- `--intent-file`: path to intent JSON inside the target repo (must include `goal`)
- `--ci-status-json`: local CI status export for capability evidence
- `--profile`: standards profile override
- `--run-id`: stable run id (refresh uses `--run-id-prefix` instead)
- `--interactive`: prompt before excluding expensive default-ignored scan paths
- `--checkout-most-advanced-branch`: switch to the local most-advanced branch first
- `--skill-review-report`: merge a validated agent skill review report into findings
- `--json`: emit machine-readable CLI output

Intent is optional. When supplied, QR writes `intent.json` and embeds the packet
on `run-manifest.json`, `agent-handoff.json`, and `run-summary.json`.

## QR Gate Controller

`gate`, `gate-status`, and `gate-respond` implement a driveable controller loop
on top of existing run artifacts. They do not re-run `refresh` and they do not
mutate source files.

```bash
quality-runner gate /path/to/repo --run-id refresh-001-verify --json
quality-runner gate-status /path/to/repo --gate-run-id gate-20260707-001 --json
quality-runner gate-respond /path/to/repo \
  --gate-run-id gate-20260707-001 \
  --action route-next-slice \
  --finding-id gate-pnpm-install \
  --notes "Run pnpm install before re-verify." \
  --json
```

`gate` requires an existing run with `agent-handoff.json`. Use `--intent` or
`--intent-file` when the source run has no intent artifact.

`gate-respond` records controller decisions in `gate-responses.jsonl`. `approve`
and `abort` close the gate run; `fix`, `skip`, `route-next-slice`, and
`record-disposition` append history while leaving the run driveable until a
terminal action is recorded.

### Disposable worktree verification

`verify-gates` and `refresh` accept:

- `--worktree-mode in-place` (default): execute gates in the target repository
- `--worktree-mode disposable`: execute gates in a detached git worktree at
  `HEAD`, write artifacts to the original repo, and discard the worktree
- `--allow-dirty-worktree-verify`: permit disposable verification when the
  source worktree has local edits

```bash
quality-runner verify-gates /path/to/repo \
  --run-id verify-disposable \
  --worktree-mode disposable \
  --allow-dirty-worktree-verify \
  --json
```

## `quality-runner propose-fix`

Writes structured fix proposals for a remediation finding group without
applying source changes.

```bash
quality-runner propose-fix /path/to/repo \
  --run-id refresh-001-verify \
  --finding-group remediate-structural-src-app-page-tsx \
  --json
```

`--finding-group` must match a remediation slice id or the current handoff
`next_slice` id. Use repeated `--finding-id` to limit proposals to specific
findings inside the group.

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
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --handoff-output handoff.md --json
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --verify-timeout-seconds 300 --json
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --total-timeout-seconds 900 --json
```

Use `--handoff-output` for the normal single-repo workflow where the scan and
the human remediation plan should be produced together. Refresh still writes the
canonical `agent-handoff.md` under `.quality-runner/runs/<prefix>-verify/`;
`--handoff-output` copies that Markdown to the requested path.

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

## `quality-runner rollout`

Runs safe single-repo refreshes across a repo list and captures controller
artifacts for each repo. Rollout is sequential by design: each repo gets its own
`quality-runner refresh` run id prefix, controller report, validation result,
and ledger row before the next repo starts.

```bash
quality-runner rollout repos.txt \
  --run-id-prefix all-projects-20260704 \
  --output-dir /private/tmp/qr-all-projects-20260704 \
  --timeout-seconds 90 \
  --verify-timeout-seconds 180 \
  --total-timeout-seconds 600 \
  --workflow-timeout-reason "all-projects stress verify deadline" \
  --total-timeout-reason "all-projects stress total deadline" \
  --json
```

Repo list formats:

- text: `/path/to/repo [baseline-run-id] [name]`
- CSV-style text: `/path/to/repo,baseline-run-id,name`
- JSON: `["/path/to/repo", {"repo_path": "/path", "baseline_run_id": "..."}]`
- repeated CLI entries: `--repo /path/one --repo /path/two`

By default, rollout preserves the read-only refresh policy and does not pass
`--allow-mutating-gates`. Each repo still writes its normal `.quality-runner/`
run artifacts, while the controller output directory receives:

- `rollout-ledger.json`
- `<index>-<repo>-controller-report.json`
- `<index>-<repo>-controller-report-validation.json`

Use `--allow-mutating-gates` only when the controller explicitly accepts source
mutation risk for the whole repo list. Invalid repo paths and refresh exceptions
are recorded as rejected or blocked controller artifacts, and the rollout
continues to the remaining repos.

## `quality-runner release-smoke`

Runs the pre-release CLI smoke path against a generated tiny repository. This is
the repeatable check for the public happy path: help text, doctor readiness,
`refresh --handoff-output`, `export-handoff`, and legacy/new controller report
schema compatibility. It also verifies the compatibility package surfaces that
ship inside `quality-runner`: `quality_evidence_contract` imports,
`repo_quality_certifier` imports, certifier artifact generation, certifier MCP
tool metadata, and packaged plugin manifests.

```bash
quality-runner release-smoke --json
quality-runner release-smoke --work-dir /tmp/quality-runner-release-smoke --json
```

The JSON result uses `quality-runner-release-smoke-result-v0.1` and includes
per-check statuses plus the generated handoff path. The handoff examples in
[`docs/examples`](examples/) show representative clean, blocked, and timeout
outputs for manual release review.

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

Prints a controller-friendly run summary with final status, `lifecycle_status`,
handoff `status`, gate table, missing capabilities, finding counts, a recommended
classification, optional embedded `intent`, and an optional baseline delta.

```bash
quality-runner summarize-run /path/to/repo --run-id final-001 --json
quality-runner summarize-run /path/to/repo --run-id final-001 --baseline-run-id baseline-001 --json
quality-runner summarize-run /path/to/repo --run-id final-001 --baseline-run-id baseline-001 --controller-report --branch-name qr/example --json
quality-runner summarize-run /path/to/repo --run-id final-001 --baseline-run-id baseline-001 --controller-report --report-output worker-report.json --lint-report --validate-report --json
```

With `--controller-report`, the command emits a strict controller-report
skeleton using the run summary, current git status, branch name, baseline path,
and inferred blockers. Workers can add explicit `--blocker`, `--file-changed`,
`--commit-hash`, `--push-status`, and `--thread-status` values.

Use `--report-output` to write the generated report to disk. With
`--lint-report` and `--validate-report`, the command runs the same strict
self-checks expected by controller waves and records their results under
`self_checks`. Generated controller reports also include `target_head`,
`commit_created_by_task`, `repo_state`, and expected lint/validate commands in
`verification`. Pass `--pre-head`, `--pre-git-status-short`, and
`--concurrency-note` when a worker captured pre-run repo state or observed the
target HEAD moving during a run.

## `quality-runner export-handoff`

Prints the latest `agent-handoff.md`, or a selected run handoff. This is useful
when regenerating or copying documentation from an existing run without running
another scan.

```bash
quality-runner export-handoff /path/to/repo
quality-runner export-handoff /path/to/repo --run-id baseline-001 --output handoff.md --json
```

## `repo-quality-certifier` Compatibility

The compatibility command preserves the prior Repo Quality Certifier verbs while
Quality Runner becomes the package to install and lead with publicly.

```bash
repo-quality-certifier plan --repo-root /path/to/repo --run-id certify-001 --json
repo-quality-certifier doc-quality --repo-root /path/to/repo --run-id certify-001 --json
```

The command writes gate-certification artifacts to
`AIOS-backfill/gate-adoption/<run-id>` by default, matching the historical
contract used by existing callers.

## Exit Behavior

- `0`: command completed successfully.
- `1`: validation or filesystem error.
- `2`: argument parsing error.

Errors are printed to stderr without Python tracebacks.
