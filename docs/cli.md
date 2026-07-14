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
terminal action is recorded. For `record-disposition`, pass `--finding-id`,
`--disposition`, `--owner`, and `--notes`; QR updates the source run's
`resolution-ledger.json` `finding_dispositions` without editing source files.

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

## Native QR planning

QR can maintain its own evidence-backed phase workflow without importing GSD
runtime behavior. These commands write only the QR-owned namespace
`.planning/quality-runner/`; they never edit source files, run remediation,
create commits, or push branches. The `--json` form is intended for agents and
controllers; the default form is a short human summary.

```bash
quality-runner plan init /path/to/repo --json
quality-runner plan status /path/to/repo --json
quality-runner phase add /path/to/repo "Capability baseline" --json
quality-runner phase plan /path/to/repo \
  --phase 1 --run-id qr-baseline-run --json
quality-runner phase next /path/to/repo --phase 1 --json
quality-runner phase record-batch /path/to/repo \
  --phase 1 --plan 1 --result-file batch-result.json --json
quality-runner phase update /path/to/repo \
  --phase 1 --baseline-run-id qr-before --run-id qr-after --json
quality-runner phase verify /path/to/repo --phase 1 --run-id qr-after --json
quality-runner phase close /path/to/repo --phase 1 --run-id qr-after --json
```

`phase plan` accepts either a QR run containing `remediation-plan.json` or an
existing `agent-handoff.json` with a resolvable remediation-plan artifact. QR
creates one `PLAN.md` per remediation cluster, assigns deterministic waves and
dependencies, and preserves existing plans. `phase next` emits the lowest
incomplete ready wave only. `phase record-batch` consumes a structured result
and writes the matching `SUMMARY.md`; the external human or agent remains
responsible for all implementation and git operations. `phase update` consumes
the current run's `remediation-delta.json` when present, or builds that
evidence from the two QR runs. `phase verify` and `phase close` require every
plan to be verified and every required check to pass.

The native files are:

```text
.planning/quality-runner/
  ROADMAP.md
  STATE.md
  config.json
  phases/<nn>-<slug>/
    <nn>-CONTEXT.md
    <nn>-<nn>-PLAN.md
    <nn>-<nn>-SUMMARY.md
    <nn>-VERIFICATION.md
```

Existing `.planning/ROADMAP.md`, `.planning/STATE.md`, and GSD phase
directories are untouched. The native configuration defaults to committing
planning documents, but QR never performs the commit.

## `quality-runner remediation-delta`

Compares two QR runs and writes a tool-neutral remediation update into the
current run. It reports new, persisted, and resolved findings; remediation
cluster changes; capability changes; package-manager evidence; and gate-state
changes. It never reads or writes project-planning files.

```bash
quality-runner remediation-delta /path/to/repo \
  --run-id current-verify \
  --baseline-run-id baseline-verify \
  --output /tmp/remediation-update.md \
  --json
```

The canonical artifacts are `.quality-runner/runs/<run-id>/remediation-delta.json`
and `remediation-delta.md`. A planning system may consume either format.

## `quality-runner skill`

Quality Skill management is split into candidate validation, pack assignment,
and corpus distribution:

```bash
quality-runner skill ingest candidate.toml \
  --repo-path /path/to/repo --id candidate --json

quality-runner skill classify candidate.toml \
  --corpus-path /path/to/personal-quality-corpus \
  --id candidate --json

quality-runner skill append candidate.toml \
  --corpus-path /path/to/personal-quality-corpus --id candidate \
  --pack-id ui-foundations --json

quality-runner skill sync \
  --corpus-path /path/to/personal-quality-corpus \
  --repo-path /path/to/repo-a \
  --repo-path /path/to/repo-b --json
```

`ingest`, `append`, and `sync` are dry-run commands unless `--write` is passed.
`classify` returns ranked advisory recommendations. `append` namespaces the
candidate's rule and review ids and records `[[sources]]` provenance. `sync`
updates only QR-owned skill files and the skill configuration block; it keeps
target-only packs and unrelated configuration. Use `--replace-active` with
`sync` only when the corpus should replace, rather than extend, the target's
active set.

## `quality-runner prune-artifacts`

Previews or applies the configured artifact retention policy. The default is a
dry run; deletion requires `--apply`.

```bash
quality-runner prune-artifacts /path/to/repo --json
quality-runner prune-artifacts /path/to/repo --apply --json
```

The command reports the configured `retention_runs` and `retention_days`, the
run directories selected for deletion, and any skipped unsafe entries. See
[Artifact Contract](artifacts.md#artifact-privacy-and-retention) for the
redaction and retention configuration.

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
- `slice-specs/` (per-slice cold-executor Markdown specs)
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
- `slice-specs/` (per-slice cold-executor Markdown specs)
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
outputs for manual release review. See
[`slice-spec-structural-harden.md`](examples/slice-spec-structural-harden.md)
for a cold-executor slice spec example.

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
target HEAD moving during a run. Pass `--batch-scope-file` with a JSON object
containing `finding_ids`, `cluster_id`, `intent_ref`, and `allowed_files` so
strict lint can reject controller reports whose `files_changed` drift outside
the declared batch scope.

## `quality-runner export-handoff`

Prints the latest `agent-handoff.md`, or a selected run handoff. This is useful
when regenerating or copying documentation from an existing run without running
another scan.

```bash
quality-runner export-handoff /path/to/repo
quality-runner export-handoff /path/to/repo --run-id baseline-001 --output handoff.md --json
```

## `quality-runner export-slice-specs`

Writes or regenerates improve-style cold-executor slice specs for an existing
run. Specs are also written automatically by `run` and `verify-gates`; use this
command when you need to refresh Markdown after copying artifacts or when an
older run predates slice-spec generation.

```bash
quality-runner export-slice-specs /path/to/repo --run-id baseline-001 --json
```

Writes one Markdown file per remediation slice under
`.quality-runner/runs/<run-id>/slice-specs/<slice-id>.md`. JSON output uses
schema `quality-runner-export-slice-specs-result-v0.1` and lists
`slice_spec_paths` plus `slice_spec_dir`.

## `quality-runner validate-handoff`

Validates an `agent-handoff.json` against schema rules and executor-readiness
checks. Use this before dispatching a worker or after regenerating handoff
artifacts.

```bash
quality-runner validate-handoff /path/to/repo/.quality-runner/runs/run-001/agent-handoff.json --json
quality-runner validate-handoff handoff.json \
  --remediation-plan remediation-plan.json \
  --json
```

Schema validation uses the same rules as workflow writes. Quality validation
additionally checks that:

- `implementation_allowed` remains `false`
- every remediation slice has machine-checkable verification
- every slice has STOP conditions and `planned_at` git state when git metadata
  is available
- structural slices anchor to file/line/fingerprint evidence

Returns `quality-runner-validate-handoff-result-v0.1` with `status`:
`passed` or `rejected`.

## `quality-runner validate-slice-spec`

Validates a generated slice-spec Markdown file for required sections and basic
content safety.

```bash
quality-runner validate-slice-spec \
  /path/to/repo/.quality-runner/runs/run-001/slice-specs/remediate-missing-typecheck.md \
  --json
```

Required sections include why this matters, current state, in/out scope, ordered
steps, per-step verification, done criteria, and STOP conditions. The linter
rejects secret-looking literals copied into Markdown.

Returns `quality-runner-validate-slice-spec-result-v0.1`.

## `quality-runner review-worker`

Read-only post-worker verification. Compares a controller/worker completion
report against a baseline QR run and a final QR run without editing source.

```bash
quality-runner review-worker /path/to/repo \
  --baseline-run-id qr-before \
  --final-run-id qr-after \
  --worker-report worker-report.json \
  --json
```

Checks include:

- worker report schema validity (`validate-report` rules)
- final `agent-handoff.json` schema and handoff quality lint
- fingerprint delta between baseline and final `code-quality-scan.json`
- changed files vs declared worker scope (warning when they diverge)

Returns `quality-runner-review-worker-result-v0.1` with `status`: `passed` or
`rejected`. QR does not apply fixes or rerun gates inside this command; it only
audits artifacts the worker already produced.

## Task-scoped implement-review deltas

An implementation agent can opt into a repeated review loop by supplying the
existing task intent plus a stable cycle id and iteration to `refresh`:

```bash
quality-runner refresh /path/to/repo \
  --run-id-prefix task-002-pass-1 \
  --intent "Implement the requested task" \
  --review-cycle-id task-002 \
  --review-iteration 1 \
  --json
```

The final verify run writes `review-delta.json` and `review-delta.md`. The
agent applies the listed task-scoped fixes, then calls `refresh` again with
`--baseline-run-id task-002-pass-1-verify` and the next iteration. A delta
recommends `stop` only when the task scope has no findings and verification is
not blocked. Unrelated findings remain visible as `out_of_scope` and do not
block the task. Quality Runner remains read-only and never applies the fixes.

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
- `1`: validation or filesystem error (`validate-handoff`, `validate-slice-spec`,
  and `review-worker` also exit `1` when `status` is `rejected`).
- `2`: argument parsing error.

Errors are printed to stderr without Python tracebacks.
## `quality-runner review`

Runs a fresh local review packet without modifying source files:

```bash
quality-runner review /path/to/repo --task "Implement the requested change" --json
quality-runner review /path/to/repo --mode blind --breadth full --no-save
```

The command defaults to `--mode task`, `--scope project`, and project breadth
`--breadth related`. It supports `--mode task|blind|combined`,
`--scope task|project`, `--breadth focused|related|full`, `--task`,
`--task-file`, `--reuse-task`, `--previous-summary`, repeated `--exclude` and
`--evidence`, `--detail`, `--save/--no-save`, `--known-issues`, `--loop`,
`--loop-stop`, `--finding-id`, `--all-critical-high`, and the local
`--adapter-output` JSON path. Task and combined modes require task input;
Quality Runner suggests blind mode when it is absent.

Human and JSON output expose mode, scope, breadth, adapter status, severity
counts, evidence limitations, and saved artifact paths. The no-issue message is
qualified: no major issues from available evidence does not prove end-to-end
correctness. Quality Runner remains local and read-only; a missing adapter is
`review-not-run`, not a completed review. Saved output includes
`review-agent-packet.md` and `review-fix-prompts.md` for separate agents.
