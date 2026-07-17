# CLI Reference

Quality Runner provides two primary console scripts:

- `quality-runner`
- `quality-runner-mcp`

It also packages compatibility console scripts for existing Repo Quality
Certifier callers:

- `repo-quality-certifier`
- `repo-quality-certifier-mcp`

## Outcome-first journeys

New users and integrations should start with `audit`, `review`, `verify`, and
`runs`. All four render a compact outcome card by default. Their v2 JSON uses
`quality-runner-outcome-v0.2` and leads with state, assessment, evidence
confidence, writes, safety, and the safest next action.

```bash
quality-runner audit /path/to/repo --json
quality-runner review /path/to/repo --mode blind --json
quality-runner verify /path/to/repo --json
quality-runner runs /path/to/repo --json
```

`inspect`, `run`, and `verify-gates` remain supported v1 compatibility commands.
`review --legacy-output` provides the established v1 review JSON field shape
when an existing CLI consumer requires it; the notice is sent to stderr so
stdout stays machine-readable. The [Upgrade and Compatibility Guide](upgrade.md)
owns the command mappings and support window. A blocked verification or
packet-ready review is a truthful v2 outcome, not a parser failure; callers
should read its `next_action` before deciding whether to run commands or request
a reviewer.

### `quality-runner audit`

`audit` is the preferred audit-and-plan entrypoint. It writes the same local
evidence family as the compatibility `run` path, then projects it into the v2
outcome. Use `--inspect-only` to create inspection evidence without preparing a
remediation plan. Neither mode edits source files. If
`--checkout-most-advanced-branch` is requested, the outcome explicitly reports
that the source worktree branch may have changed.

### `quality-runner verify`

`verify` is the preferred verification entrypoint. It records gate evidence by
default and reports that state as evidence-only. Running discovered commands
requires both `--execute-gates` and `--worktree-mode disposable`; the outcome
labels successful execution as disposable only when the saved verification
record proves it. A disposable checkout protects the source worktree from
ordinary mutations, but it is not a host sandbox.

### `quality-runner runs`

`runs` is a bounded read-only history view. It never writes `run-summary.json`.
Use `--run-id` for one run or `--limit` to constrain recent history. Its outcome
includes the bounded run IDs and statuses it read, plus truncation and unreadable
run signals. Missing or unreadable selected runs become limited evidence rather
than a clean result.

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

[quality_runner.scan_exclusions_by_module]
code_quality = ["generated-output/**"]
# security remains enabled for generated-output/**
```

These augment the default exclusions for fixtures, corpora, docs, vendored
trees, and tool output directories. `scan_exclusions` is the backward-compatible
all-module list. The module table supports `structural`, `code_quality`, and
`security`; module-specific entries add exclusions only to that QR-owned
scanner.

## `quality-runner exclusions`

Builds and reviews a deterministic scan-exclusion candidate packet. Suggestion
is review-only and does not edit repository configuration:

```bash
quality-runner exclusions suggest /path/to/repo --run-id exclusions-001 --json
quality-runner exclusions validate /path/to/repo \
  --packet /path/to/repo/.quality-runner/runs/exclusions-001/scan-exclusion-preflight-packet.json \
  --report /path/to/review.json --json
quality-runner exclusions apply /path/to/repo \
  --packet /path/to/repo/.quality-runner/runs/exclusions-001/scan-exclusion-preflight-packet.json \
  --report /path/to/review.json --apply --json
```

Packets include tracked/ignored status, file counts, generated/artifact
markers, estimated scan cost, and configuration/timeout signals. Reports are
bound to the packet and repository fingerprint, require one decision per
candidate, and reject traversal, globs, stale fingerprints, and protected
source/security/config roots. `apply` is the only mutating stage and requires
the explicit `--apply` flag.

Unwired-work checks can also be configured. They run as structural category
`integrate` and produce decision-based remediation slices; see
[Unwired Work Detection](unwired-work.md).

## Shared Workflow Flags

`audit`, `inspect`, `run`, `verify`, `verify-gates`, and `refresh` share these
arguments where they apply:

- `--intent`: short author goal for the run (what the user set out to accomplish)
- `--intent-file`: path to intent JSON inside the target repo (must include `goal`)
- `--ci-status-json`: local CI status export for capability evidence
- `--profile`: standards profile override
- `--run-id`: stable run id (refresh uses `--run-id-prefix` instead)
- `--interactive`: prompt before excluding expensive default-ignored scan paths
- `--scan-exclusion DIR`: exclude this repo-relative directory for this run
  only; repeat for multiple directories. This is a global overlay and changes
  security scan coverage without editing repository configuration.
- `--scan-exclusion-module MODULE=DIR`: exclude this repo-relative directory
  for one QR-owned module only; use `structural`, `code_quality`, or `security`.
  Structural and code-quality overlays preserve security coverage.
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

Discovered commands are evidence-only by default. To run them, callers must
supply both `--execute-gates` and `--worktree-mode disposable`. An execution
request with `in-place` mode is rejected. Disposable mode verifies `HEAD` in a
separate checkout and removes that checkout afterward; it protects the ordinary
source worktree from normal gate mutations, but it is not a host sandbox for an
arbitrary authorized command.

`--allow-dirty-worktree-verify` permits a disposable verification against
`HEAD` while retaining local source edits. It does not verify those edits.

```bash
quality-runner verify-gates /path/to/repo \
  --run-id verify-disposable \
  --execute-gates \
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

QR can maintain an evidence-backed phase workflow without importing GSD runtime
behavior. These commands write only `.planning/quality-runner/`; they never
edit source files, run remediation, create commits, or push branches. The
`--json` form is intended for agents and controllers.

```bash
quality-runner plan init /path/to/repo --json
quality-runner plan status /path/to/repo --json
quality-runner plan auto /path/to/repo --run-id qr-baseline-run --json
quality-runner phase next /path/to/repo --phase 1 --json
quality-runner phase record-batch /path/to/repo \
  --phase 1 --plan 1 --result-file batch-result.json --json
quality-runner phase update /path/to/repo \
  --phase 1 --baseline-run-id qr-before --run-id qr-after --json
quality-runner phase verify /path/to/repo --phase 1 --run-id qr-after --json
quality-runner phase close /path/to/repo --phase 1 --run-id qr-after --json
```

`plan auto` initializes the namespace when needed, creates one native phase per
domain candidate in security-first order, and links each phase to its forensic
leaf slices. It is idempotent and advisory-only. `phase plan` can consume a QR
run or an existing handoff; it uses domain `phase_candidates` when present and
falls back to older remediation clusters. QR assigns deterministic waves and
dependencies, preserves existing plan text, and leaves implementation and git
operations to the external agent or human.

Native files live under:

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
directories are untouched. GSD and other planning systems remain optional
consumers of the canonical QR artifacts.

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

Records discovered command-backed gates and their execution plan without
applying remediation. By default every executable gate is skipped with
`execution-consent-required`; this is a blocked evidence state, not a command
failure. CI-only and file/evidence capabilities remain non-executable evidence.
When explicitly authorized in disposable mode, JavaScript package scripts run
through the detected package manager.

```bash
quality-runner verify-gates /path/to/repo --run-id verify-001 --json
quality-runner verify-gates /path/to/repo --timeout-seconds 300 --json
quality-runner verify-gates /path/to/repo --execute-gates --worktree-mode disposable --json
```

Repos can override individual gate timeouts in `.quality-runner.toml`:

```toml
[quality_runner.gate_timeouts]
tests = 300
pre_cr = 600
```

Configured `[[quality_runner.gates]]` may set `mutating_risk` to `safe`,
`unknown`, or `mutating`. Under `--read-only-gates`, `unknown` and `mutating`
gates stay skipped unless `--allow-mutating-gates` is also explicit.

Possible verification statuses include `passed`, `passed-with-findings`,
`failed`, `blocked`, and `skipped-nonlocal`.

`verify` uses these same gate semantics but projects the result into an additive
outcome. It remains evidence-only until explicit disposable execution is
authorized, so a blocked outcome should be acted on through its displayed next
command rather than interpreted as a passed gate.

Writes:

- `repo-scan.json`
- `code-quality-scan.json`
- `package-manager-preflight.json`
- `standards.json`
- `capability-matrix.json`
- `gate-execution-plan.json`
- `gate-verification.json`
- `quality-audit.json`
- `remediation-plan.json`
- `slice-specs/` (per-slice cold-executor Markdown specs)
- `agent-handoff.json`
- `agent-handoff.md`
- `run-manifest.json`

## `quality-runner refresh`

Runs `inspect`, `run`, `verify-gates`, and `summarize-run` as one
controller-friendly workflow. Its default verification is evidence-only; use
the same explicit disposable-execution pair when command proof is required.

```bash
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --handoff-output handoff.md --json
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --verify-timeout-seconds 300 --json
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --total-timeout-seconds 900 --json
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --execute-gates --worktree-mode disposable --json
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
Default command-backed gates are classified as `execution-consent-required` and
surface in `gates-blocked` until explicit execution is authorized. Blocked and failed handoffs include `gate_verification.blocker_groups` and
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

By default, rollout preserves evidence-only refresh verification. To execute
gates across the list, pass `--execute-gates --worktree-mode disposable`; each
repo still writes its normal `.quality-runner/`
run artifacts, while the controller output directory receives:

- `rollout-ledger.json`
- `<index>-<repo>-controller-report.json`
- `<index>-<repo>-controller-report-validation.json`

`--allow-mutating-gates` is an advanced compatibility flag, not execution
authorization. Invalid repo paths and refresh exceptions
are recorded as rejected or blocked controller artifacts, and the rollout
continues to the remaining repos.

## `quality-runner release-smoke`

Runs the pre-release CLI smoke path against a generated tiny repository. This is
the repeatable package-contract check for help text, doctor readiness, the v2
inspection outcome, `refresh --handoff-output`, `export-handoff`, and
legacy/new controller report schema compatibility. It also verifies the
compatibility package surfaces that ship inside `quality-runner`:
`quality_evidence_contract` imports,
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

## `quality-runner validate-remediation-context`

Validates the bounded remediation context packet before an external worker
starts source changes. Fresh QR packets are intentionally rejected until each
selected slice has the required behavior, scope, uncertainty, characterization,
and risk-appropriate verification evidence.

```bash
quality-runner validate-remediation-context remediation-context.json \
  --remediation-plan remediation-plan.json \
  --json
```

Returns `quality-runner-validate-remediation-context-result-v0.1` with
`status: passed` or `status: rejected` and the computed readiness summary.

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
contract used by existing callers. Run ids and generated output paths are
validated; explicit output directories are never followed through symlinks, and
the compatibility command does not edit Git ignore configuration.

## Exit Behavior

- `0`: command completed successfully.
- `1`: validation or filesystem error (`validate-handoff`, `validate-slice-spec`,
  and `review-worker` also exit `1` when `status` is `rejected`).
- `2`: argument parsing error.

Errors are printed to stderr without Python tracebacks.
## `quality-runner review`

Fresh Review is a local, two-phase evidence workflow. It never edits source
files: Quality Runner first prepares an immutable context package, then a
locally supplied response is validated against that exact package.

```bash
quality-runner review /path/to/repo --mode blind --run-id review-001 --loop --json
# Fill the generated response template and submit the packet-bound local response.
quality-runner review /path/to/repo --run-id review-001 \
  --adapter-output .quality-runner/runs/review-001/review-adapter-response.json \
  --finding-id R-001 --loop-stop critical-high --json
```

The command defaults to `--mode task`, `--scope project`, and project breadth
`--breadth related`. Task and combined modes require task input; Quality Runner
suggests blind mode when it is absent. The exact parser and MCP input schema are
the source of truth for available options.

Preparation writes the packet (`review-agent-packet.md`), response template,
and lifecycle record under the selected run. The response must carry the run id,
mode, and packet hash from that template; a stale, cross-run, malformed, or
path-escaped response is kept as incomplete evidence rather than turned into a
clean review. `--task-file` must be a bounded regular file inside the target
repository. `--no-save` is a local preview only and cannot accept a later
adapter response.

Combined mode uses separately scoped task and blind packets and responses.
Quality Runner validates both responses before grouping findings locally, so task
text is never placed in the blind packet. The versioned response schema in
`quality_runner/schemas/` defines the machine contract.

The saved v1 report artifacts and `--legacy-output` JSON expose mode, scope,
breadth, adapter status, severity counts, evidence limitations, and artifact
paths without v2-only fields. The default v2 result presents the same state
through the outcome contract. A completed review with no findings uses the
qualified no-issue message. A missing adapter is packet-ready evidence, not a
completed review, and does not produce finding-specific fix prompts.

Use `--finding-id` to select the work a separate fixing agent may receive, or
use the explicit critical/high shortcut. Without a selection, the completed
report remains evidence and the handoff asks for a decision. Pass `--loop` when
preparing the packet to start a manual cycle; response submission derives that
state from the saved packet and may set `--loop-stop`. Neither flag invokes a
fixer; the next iteration is another fresh review. Exclusions describe the
intended review boundary, but a
local file adapter is external to Quality Runner, so its file access is recorded
as advisory rather than claimed as enforced.

Review emits the v2 journey projection by default. Packet-only review is
`awaiting-evidence` with `assessment: packet-ready`; it is never shown as clean.
`--outcome` remains a harmless alias. Use `--legacy-output` only when an
existing CLI consumer requires the frozen v1 field shape; it emits a versioned
stderr notice. The [Upgrade and Compatibility Guide](upgrade.md) defines the
support window and rollback path.
