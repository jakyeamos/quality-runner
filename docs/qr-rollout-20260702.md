# QR Rollout 20260702

Source report: `/private/tmp/quality-runner-readable-report-20260702.md`

- Base run id: `parallel-20260702T200935Z`
- Branch: `qr/clean-audit-parallel-20260702T200935Z`
- Wave size: 5
- Scope: 44 repos from the report
- Excluded: `soundscape-app`
- Restarted wave 1 runner: `/Users/jakyeamos/projects/quality-runner/.venv/bin/quality-runner`

## Controller Protocol

Repo threads must work only inside their assigned repo path and report one of
`complete` or `blocked` before stopping. The controller records the report in
this ledger before starting the next wave.

`complete` means the final Quality Runner run status is `clean`. `blocked`
means the worker attempted full remediation and documented a concrete hard
blocker, such as missing credentials or env secrets, an unsafe or destructive
domain decision that requires owner input, dependency or network impossibility,
a QR scanner limitation that cannot be configured around without disabling the
relevant signal wholesale, or test/build failures outside touched scope after
reasonable targeted remediation.

Required thread report fields:

- repo path
- branch name
- Codex project status
- baseline artifact path
- final QR run id and status
- files changed
- verification commands and results
- commit hash
- push status
- blockers or follow-up notes

Codex project resolution:

1. Use an exact Codex project when available.
2. Otherwise use the saved parent project `/Users/jakyeamos/projects` and
   constrain the thread to the exact repo path.
3. If neither is available, mark `needs-codex-project` and do not start that
   repo thread.

## Wave 1 Retrospective

Wave 1 is closed. Four repos were blocked by broad repo-owned structural debt
after the fixed runner removed scanner-scope noise, and one repo (`Vaults`) ran
clean. Early worker reports used `ready-for-review` after clearing missing
repo-owned gates but before clearing runner-provided findings. The controller
tightened the terminal vocabulary so partial progress remains `running` and gets
returned to the worker.

Product improvements found:

- Quality Runner recommended `pnpm audit:dead-code` but did not recognize
  `audit:dead-code` as a `dead_code` package script. The detector now accepts
  the recommended script name.
- Several repos needed repo-specific scan exclusions for generated,
  operational, or third-party paths. Current Quality Runner source applies
  `scan_exclusions` to the structural scanner; workers using an older installed
  CLI may need to rebuild or reinstall the current checkout before rerunning.
- Hidden operational/governance folders (`.aios`, `.planning`, `.superpowers`,
  `.tracker`) are now excluded from structural scanning by default. Workers
  should only re-include them with
  `quality_runner.structural_scan.include_ignored_paths` when those folders are
  the intended source under review.
- Workers need a stricter final report: if QR status is not `clean`, they must
  classify the remaining findings as a blocker with evidence, not as a
  successful completion.

## Triage Wave Protocol

The original cleanup-wave rollout is paused. The remaining repos should be run
as a case-study triage sample, not as an attempt to make every mature repo
Quality Runner clean in one pass.

Triage worker objective:

- Classify the repo outcome as `clean`, `missing-gates-only`,
  `scanner-product-issue`, `broad-repo-debt`, `env-or-dependency-blocker`, or
  `mixed-blocker`.
- Use `/Users/jakyeamos/projects/quality-runner/.venv/bin/quality-runner` and
  verify version `0.2.1` before running QR.
- Remediate only missing repo-owned gates, obvious path/scope configuration
  issues, and at most 1-3 high-signal findings that are clearly safe.
- Stop early when QR shows broad structural debt rather than attempting a
  sweeping refactor.
- Do not disable whole structural rule groups to get a clean result.
- Do not commit `.quality-runner/` artifacts unless already tracked.
- Report classification, final QR run id/status, files changed, verification,
  commit/push state, and product lessons back to the controller.

Triage acceptance:

- The sample has a terminal classification for each repo.
- The ledger records whether QR was clean, blocked by product/scanner behavior,
  blocked by environment/dependency access, or blocked by repo-scale debt.
- The case study emphasizes staged adoption lessons instead of treating every
  non-clean result as a failed cleanup.

## Triage Sample Results

The first two paused-wave samples are closed. Each repo thread reported a
terminal outcome to the controller before the corresponding ledger rows were
updated.

Observed classifications:

- Wave 2 `broad-repo-debt`: `Dsci-proj`, `Bballedu`, `Fantasy`
- Wave 2 `mixed-blocker`: `BBDSE`, `EliHealth`
- Wave 3 `broad-repo-debt`: `Book`, `dispatches-from-cyberspace`,
  `video-pipeline`
- Wave 3 `mixed-blocker`: `portfolio`
- Wave 3 `env-or-dependency-blocker`: `remodelvision`
- Wave 4 `scanner-product-issue`: `Hoopscout`
- Wave 4 `mixed-blocker`: `pre-cr-suite-lsp`, `career-ops`, `Crimclock`,
  `Crimclock-pr1-audit`

Cross-repo lessons:

- Missing-gate remediation is usually tractable when the repo already has
  equivalent checks under non-canonical names. Aliases or QR config can clear
  capability gaps without broad code changes.
- QR needs to separate three states in its product language: capability is
  discoverable, capability command executes, and capability command passes.
- QR traversal still needs product hardening. Several repos were slowed or
  blocked before artifact creation because discovery walked dependency,
  generated, cache, or nested-project surfaces before pruning.
- `scan_exclusions` and default ignored-path behavior help only if applied
  before recursive traversal and stat calls.
- Mature repos commonly move from missing capabilities to broad structural
  backlog. The case study should present this as staged adoption, not as a
  failed cleanup wave.
- `verify-gates` exposed the next Tier 1 product seam: discovered package
  scripts and CI-derived gates are not yet the same thing as locally executable
  gate commands.

Product fixes applied before the next triage wave:

- Discovery and mature-surface detection now use a pruned recursive iterator so
  dependency, generated, cache, vendored, fixture, and configured exclusions are
  skipped before descent rather than filtered after `rglob`.
- Root `.gitignore` entries are now folded into traversal pruning so untracked
  ignored dependency/generated/cache trees do not become repo surfaces.
- Capability artifacts now include `verification_state`, separating discovery
  evidence from command execution evidence and pass/fail evidence.
- `quality-runner verify-gates` now executes discovered command-backed gates and
  writes `gate-verification.json`; inspect/run remain discovery and planning
  workflows.
- `package-manager-preflight.json` now records package-manager declaration,
  lockfiles, and mixed-lockfile warnings for every inspect/run/verify workflow.
- `quality-runner validate-report` now rejects controller reports that claim
  terminal completion while `git_status_short` still contains staged or
  uncommitted changes.
- Remediation plans and agent handoffs now include adoption stage and stopping
  criteria so threads know whether to stop after gates, scope fixes, high-signal
  findings, or debt classification.

## Wave 1 Restart Protocol

Wave 1 is being restarted after Quality Runner product fixes on branch
`codex/structural-scan-exclusions`.

Worker requirements for the restart:

- Use `/Users/jakyeamos/projects/quality-runner/.venv/bin/quality-runner` for
  every final QR run, not a globally installed `quality-runner` binary.
- Run `quality-runner --version` first and require version `0.2.1`.
- Preserve existing repo branch commits and unrelated dirty work.
- Continue from the existing QR branch when present.
- Do not disable whole structural rule groups merely to make QR green unless
  the repo is genuinely a non-code/content container and the reason is
  documented in the repo config and final report.
- Terminal status remains only `complete` when final QR is clean, or `blocked`
  with a hard blocker and evidence.

## Wave 4 Stress Protocol

Wave 4 is a product stress wave, not a cleanup wave. Workers should preserve
dirty repo work, avoid broad remediation, and exercise the current runner's
`inspect`, `run`, `verify-gates`, `package-manager-preflight.json`,
`gate-verification.json`, handoff status, and `validate-report` paths. The
primary output is a Tier 1 product-risk finding list: traversal failures,
ignored/generated/cache leakage, package-manager confusion, gate execution
misclassification, misleading handoff state, invalid/missing artifacts, or
controller-report validation gaps.

Wave 4 stress takeaways:

- Traversal hardening mostly held. Workers did not report stalls, and QR skipped
  `.quality-runner`, `.git`, `node_modules`, `.next`, caches, coverage, venvs,
  and generated files across the sample.
- `verify-gates` should execute package scripts through the detected package
  manager, not by shelling raw script bodies. `pre-cr-suite-lsp` and
  `Hoopscout` both failed gates that pass under `pnpm`/`corepack pnpm` because
  the raw command lacked package-manager bin context.
- CI-only discovery must be separated from local execution. `Crimclock` and
  `Crimclock-pr1-audit` discovered `github-actions pull_request quality` and
  tried to execute it as a local shell command.
- Gate failure artifacts need better diagnostics. At least one worker reported
  failed gates with null stdout/stderr tails, forcing manual reruns to diagnose
  the actual `ENOENT` cause.
- Handoff/status semantics lag behind gate verification. `run` handoffs remain
  `planned` and centered on missing gates even after `verify-gates` reveals
  executable-gate failures.
- `validate-report` correctly rejects `complete`/`ready-for-review` reports
  with dirty `git_status_short`, but the contract should document that read-only
  dirty-repo stress results must be `blocked`.
- Structural heuristics still have Tier 1 precision issues. TypeScript nullish
  coalescing, union types, regex alternation, and template expressions were
  reported as `nested-ternary` in Crimclock repos.

Product fixes applied after Wave 4:

- JavaScript package-script gates now execute through the detected package
  manager, for example `pnpm run lint`, instead of shelling raw script bodies.
- Generic pull-request workflow discovery is marked `local_execution:
  "ci-only"` and `verify-gates` skips it rather than attempting to execute a
  fake local `github-actions` command.
- `verify-gates` now writes audit/remediation/handoff artifacts using the
  verified capability matrix, and `quality-runner status` reports failed or
  blocked gate verification as repo status `blocked`.
- `gate-verification.json` now includes bounded `stdout_tail` and `stderr_tail`
  fields for executed gates.
- The `nested-ternary` rule now ignores optional chaining, nullish coalescing,
  and optional TypeScript property markers when counting ternary operators.

Wave 5 stress takeaways:

- The Wave 4 product fixes held across the sample. JavaScript package scripts
  executed through the detected package manager, CI-only pull-request gates were
  skipped instead of executed, `verify-gates` wrote the expanded artifact set,
  and `quality-runner status` reported blocked after failed verification.
- Scoped cleanup could clear repo-owned missing capabilities in all five repos.
  Four repos still ended blocked by broad structural findings or an environment
  execution issue; `R-Project` reached clean audit and passed gate verification.
- Follow-up fixes after Wave 5 separated local commands from evidence/file
  capabilities so `truth_file` no longer blocks `verify-gates`, added
  per-gate timeouts, skipped already-covered aggregate gates, added environment
  restriction classification, and introduced `summarize-run` for controller
  reports and baseline deltas.
- Localhost and subprocess-heavy tests remain a Tier 1 stress point. The
  follow-up classifier handles some QR-spawned environment failures, but the
  post-Wave 5 canary below showed that server/test timeouts can still be
  reported as ordinary command failures when the same command passes directly.
- `nested-ternary` precision improved for optional/nullish TypeScript syntax
  and regex non-capturing groups like `(?:...)`.

## Post-Wave 5 Canary

Before launching the next full cleanup wave, run a 3-repo canary against the
QR product fixes in controller commit `ace0e1f`. The canary should prefer
read-only verification over remediation and must use:

- `quality-runner inspect`, `run`, and `verify-gates` with `canary-20260703-*`
  run ids.
- `quality-runner summarize-run --baseline-run-id ... --json` in every worker
  report.
- `quality-runner validate-report --json` against a temporary controller report.
- Separate final sections for repo outcome and QR product observations.
- `ignored_generated_artifacts = [".quality-runner/"]` when generated QR
  artifacts are the only dirty paths.

Canary advancement rule: do not launch the next full wave until all three
canary reports are read by the controller and either validate cleanly or have
explicit product blockers recorded.

| Canary | Repo | Purpose | Thread status | Thread id | Final QR status | Validate-report | Notes |
|---:|---|---|---|---|---|---|---|
| 1 | `R-Project` | No-remediation canary for non-JS gates, file/evidence capabilities, and clean summary output. | complete | `019f2628-af18-7a92-8367-29f7c0597462` | `passed`; `canary-20260703-R-Project-verify`; audit `clean` | accepted | No blocker. `summarize-run` reported `recommended_classification=clean`, 0 findings, 0 missing capabilities, and no baseline deltas. `verify-gates` skipped evidence/file-only `truth_file`, recorded environment and timeout metadata, and passed the executable R gate. Product note: `gate-verification.json` still has top-level `run_id: null`, though manifest and summary carry the run id. |
| 1 | `eslint-plugin-anti-slop` | Canary for pnpm gate execution, aggregate-gate skipping, CI-only/non-command skips, and regex `nested-ternary` precision. | blocked | `019f2628-b461-71b0-8377-4426e65008b0` | `passed-with-findings`; `canary-20260703-eslint-plugin-anti-slop-verify`; gates passed | accepted | Repo blocker only: `recommended_classification=broad-repo-debt`, 6 grouped findings unchanged from baseline. Product checks held: package scripts executed as `pnpm run ...`, `pre_pr` skipped as CI-only, `truth_file` skipped as evidence-only, aggregate `pre_cr` skipped, missing capabilities stayed at 0. Regex precision improved: `(?:...)` produced 0 nested-ternary hits; remaining 2 nested-ternary hits were real ternary chains. |
| 1 | `BIP-Console` | Canary for environment-restricted QR subprocess/server failures and direct-vs-QR comparison. | blocked | `019f2628-bea5-7ec1-8178-77b12766646c` | `failed`; `canary-20260703-BIP-Console-verify2`; status `blocked` | accepted | Product blocker: direct `pnpm run test` passed 6 files / 81 tests in 4.30s, but QR-spawned `pnpm run test` failed after 108.717s with 11 timeout/server-not-running failures. QR recorded `failure_type=command-failed` with no environment-restricted classification or rerun guidance. Package-manager execution, aggregate skipping, `quality-runner status`, `summarize-run`, and ignored generated artifacts behaved correctly. |

Initial canary result: do not expand to a full wave yet. The controller read
all three reports and all temporary controller reports validated, but
`BIP-Console` exposed a Tier 1 product gap in QR-spawned environment failure
classification.

Post-canary fix:

- QR now treats test commands that fail with both timeout wording and
  server/local-subprocess symptoms as `environment-restricted` and adds
  direct-rerun guidance instead of reporting an ordinary `command-failed`.
- `gate-verification.json` now records the verification `run_id` directly.
- Regression tests cover the BIP-style server timeout classification and keep
  plain assertion failures classified as `command-failed`.
- BIP-Console rerun `canary-20260703-BIP-Console-classifier-fix-verify`
  passed all executable gates, skipped aggregate `pre_pr`/`pre_cr`, and
  `quality-runner status` reported `ready`. `summarize-run` reported
  `passed-with-findings`, `recommended_classification=broad-repo-debt`, 10
  findings unchanged from `canary-20260703-BIP-Console-verify2`, and 0 missing
  capabilities.

Expansion note: the specific QR-spawned test blocker is cleared in the latest
BIP rerun. Any next wave should still treat broad repo debt as a triage outcome,
not a cleanup failure.

## Shallow Evidence Refresh

Previous cleanup/triage waves should be rerun shallowly before another broad
wave. The refresh objective is current evidence with the latest QR runner, not
remediation.

Refresh worker rules:

- Use `/Users/jakyeamos/projects/quality-runner/.venv/bin/quality-runner` from
  controller commit `a585f9b`.
- Do not edit, stage, commit, push, or remediate repo files.
- Generated `.quality-runner/` artifacts are allowed and must remain
  uncommitted.
- Run `inspect`, `run`, `verify-gates`, `summarize-run --json`, and
  `validate-report --json`.
- Classify the final state as current `clean`, `broad-repo-debt`,
  `environment-or-runner-blocker`, `failing-executable-gates`,
  `missing-capabilities`, or `needs-triage`.
- Treat broad repo debt as a valid triage outcome, not as a failed refresh.

| Refresh wave | Repo | Repo path | Baseline run | Thread status | Thread id | Final QR status | Validate-report | Notes |
|---:|---|---|---|---|---|---|---|---|
| 1 | `tenure` | `/Users/jakyeamos/projects/tenure` | `wave1-restart-20260702-tenure-targeted` | blocked | `019f2646-6119-7de3-b58e-810b1c5f8d25` | `blocked`; `refresh-20260703-tenure-verify` | accepted | Classification `mixed-blocker`. Findings unchanged at 31 grouped, 0 missing capabilities. `lint`, `typecheck`, `dead_code`, and `runtime_smoke` passed; `formatter` and `build` timed out; `tests` was `environment-restricted` from localhost/server-port failures. Product issue: QR `formatter` gate mutated tracked files during a read-only refresh; worker restored QR-created formatter changes while preserving pre-existing `.aios/audit/*` dirtiness. |
| 1 | `BidCamp` | `/Users/jakyeamos/projects/BidCamp` | `wave1-restart-20260702-BidCamp-2` | blocked | `019f2646-69d9-7bb3-8dce-28e4003dbfcf` | `failed`; `refresh-20260703-BidCamp-verify` | accepted | Classification `mixed-blocker`. Findings unchanged at 30 grouped, 0 missing capabilities. Build failed on restricted Google Fonts fetches; formatter/lint/typecheck/tests/dead-code/runtime-smoke passed. Product issue: QR `formatter` gate ran `eslint --fix .` and mutated five clean files; worker restored those and preserved pre-existing script/data dirtiness. |
| 1 | `AIOS` | `/Users/jakyeamos/projects/AIOS` | `wave1-restart-20260702-AIOS` | blocked | `019f2646-7846-7150-986c-145d7898d1d2` | `blocked`; `refresh-20260703-AIOS-verify` | accepted | Classification `environment-or-runner-blocker`. Findings dropped from 23 to 22 grouped, 0 missing capabilities. Four gates were `environment-restricted` due to `uv` cache access under sandbox permissions; formatter/lint/typecheck expose repo-owned debt; build also hit blocked Google Fonts fetches and a Turbopack/NFT trace warning. |
| 1 | `amos-saas` | `/Users/jakyeamos/projects/amos-saas` | `wave1-restart-20260702-amos-saas` | blocked | `019f2646-81b3-7091-b4d7-5d7f6c6283fd` | `failed`; `refresh-20260703-amos-saas-verify` | accepted | Classification `mixed-blocker`. Findings unchanged at 27 grouped, 0 missing capabilities, 972 raw findings across 241 scanned files. All local `pnpm run ...` gates failed before scripts because pnpm attempted non-TTY module purge/install and raised `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY`; `pre_pr` skipped as CI-only. |
| 1 | `Dsci-proj` | `/Users/jakyeamos/projects/Dsci-proj` | `triage-20260702-Dsci-proj` | blocked | `019f2646-8a93-72d3-b68c-fe79feb6eb80` | `failed`; `refresh-20260703-Dsci-proj-verify` | accepted | Classification `failing-executable-gates`. Findings unchanged at 13 grouped, 0 missing capabilities. Ruff format/lint failed in `pipeline`; dashboard tests failed because `jsdom` is missing; dashboard build/typecheck/dead-code gates failed under QR with `tsc`/`next` not found. Product issue: package-manager preflight missed nested dashboard `package-lock.json`, and QR executed subproject script bodies without local `.bin` resolution. |

Refresh wave 1 takeaways:

- Current runner evidence is materially better than the original cleanup waves:
  all five workers produced summaries, baseline deltas, and accepted controller
  reports.
- None of the refreshed repos are clean. The sample is useful as current
  blocker evidence rather than advancement evidence.
- Broad structural debt is stable across the sample: `tenure`, `BidCamp`,
  `amos-saas`, and `Dsci-proj` had unchanged grouped finding counts; `AIOS`
  improved by one grouped finding.
- `verify-gates` is not safe for read-only refresh when a formatter script is
  mutating, such as `eslint --fix` or equivalent. QR needs either a non-mutating
  formatter detection mode or a read-only gate policy before broader evidence
  sweeps.
- Environment/network classification is improving, but still incomplete:
  localhost/server-port and `uv` cache failures were classified, while Google
  Fonts fetch failures remained ordinary command failures in some gates.
- Package-manager handling still needs nested-project hardening. `Dsci-proj`
  showed subproject lockfiles and local `.bin` resolution gaps; `amos-saas`
  showed pnpm non-TTY install/purge behavior before scripts could run.

## Product Fixes Before Refresh Wave 2

The ten requested QR improvements are implemented before rerunning the shallow
wave:

- `verify-gates --read-only-gates` and `refresh` default to a read-only gate
  policy that skips formatter or unknown-risk commands instead of mutating the
  target repo.
- `verify-gates --allow-mutating-gates` is the explicit override for mutating
  gates, giving controller threads a visible approval point.
- Formatter scripts now carry mutating-risk metadata when discovery can tell a
  script is mutating or ambiguous.
- Gate verification writes `gate-execution-plan.json` and embeds the plan in
  `gate-verification.json`, including cwd, package manager, timeout, mutating
  risk, and local execution status.
- Google Fonts, `next/font`, fetch, DNS, localhost/socket, and sandbox-style
  failures classify as `environment-restricted` with direct rerun guidance.
- pnpm non-TTY module purge/install failures classify as
  `dependency-setup-blocker`, not ordinary command failure.
- Nested JavaScript workspaces use their own lockfile/package-manager context
  when discovering scripts.
- Package-manager preflight records nested lockfiles so controller reports can
  distinguish root package-manager state from subproject state.
- `summarize-run` persists `.quality-runner/runs/<run-id>/run-summary.json` for
  downstream controller evidence.
- Timeout diagnostics now include captured output lengths and a process snapshot
  to separate stuck commands from QR environment mismatches.
- `quality-runner refresh` runs inspect, run, read-only verify-gates, and
  summary generation as one controller-friendly workflow.

Validation before launch: `uv run ruff check .`, targeted workflow/CLI/artifact
tests, and full `uv run pytest` all pass on controller commit `9f8d85b`.

Refresh wave 2 reruns the same five repos as wave 1 with `quality-runner
refresh`, no remediation, and no target-repo commits. The point is to stress the
new read-only execution policy and classification behavior against the known
failure cases.

| Refresh wave | Repo | Repo path | Baseline run | Thread status | Thread id | Final QR status | Validate-report | Notes |
|---:|---|---|---|---|---|---|---|---|
| 2 | `tenure` | `/Users/jakyeamos/projects/tenure` | `refresh-20260703-tenure-verify` | blocked | `019f2662-b93c-7b12-8911-acdc9aa9f034` | `interrupted_after_hang`; requested `refresh2-20260703-tenure-verify` | accepted | `refresh` produced `refresh2-20260703-tenure-run` with `findings` and 31 findings, then hung inside gate verification beyond the 120s gate timeout. The verify directory exists but is empty: no `gate-execution-plan.json`, `gate-verification.json`, or `run-summary.json`. No new tracked file paths appeared; pre-existing `.aios/audit/*` modifications and untracked `.quality-runner/` remained. |
| 2 | `BidCamp` | `/Users/jakyeamos/projects/BidCamp` | `refresh-20260703-BidCamp-verify` | blocked | `019f2662-f159-7a62-983d-db9ef9d923e5` | `blocked`; requested `refresh2-20260703-BidCamp-verify` | accepted | `refresh` produced inspect/run artifacts, but the verify directory is empty and the process had to be terminated after exceeding the delegated timeout with no final JSON. Last complete run `refresh2-20260703-BidCamp-run` reported findings and 2,476 unresolved ledger entries. No new tracked changes; pre-existing script modifications and untracked `.quality-runner/`/`data/` remained. |
| 2 | `AIOS` | `/Users/jakyeamos/projects/AIOS` | `refresh-20260703-AIOS-verify` | blocked | `019f2663-26df-7ab0-b2c3-f1ec56d92c4f` | `blocked`; `refresh2-20260703-AIOS-verify` | accepted | Read-only refresh completed and wrote the execution plan, verification, and summary. Classification `environment-or-runner-blocker`; 22 findings, delta 0, missing capabilities 0. Formatter/lint/typecheck failed as command failures; `uv` cache permission errors and Google Fonts fetch failures were classified as environment restrictions. No tracked file changes. |
| 2 | `amos-saas` | `/Users/jakyeamos/projects/amos-saas` | `refresh-20260703-amos-saas-verify` | blocked | `019f2663-5d6a-7803-a3b5-76682f3aec21` | `blocked`; `refresh2-20260703-amos-saas-verify` | accepted | Read-only refresh completed and classified pnpm non-TTY dependency restoration as `dependency-setup-blocker`. Formatter and `pre_cr` were skipped with `mutating-gate-not-run`; findings stayed at 27 with zero baseline delta and no missing capabilities. No tracked file changes. |
| 2 | `Dsci-proj` | `/Users/jakyeamos/projects/Dsci-proj` | `refresh-20260703-Dsci-proj-verify` | blocked | `019f2663-9562-7f00-9ef0-4c4892726848` | `failed`; `refresh2-20260703-Dsci-proj-verify` | accepted | Read-only refresh completed with final classification `failing-executable-gates`; 13 findings, delta 0, missing capabilities 0. Runtime smoke passed; formatter, lint, typecheck, tests, build, and dead-code failed. Dashboard gates still execute through discovered npm commands inside the nested dashboard, so package-manager normalization remains incomplete. No tracked file changes. |

Refresh wave 2 takeaways:

- The read-only policy worked: no worker reported QR-created tracked source
  edits, and known/ambiguous mutating gates were skipped rather than executed.
- The pnpm non-TTY case is now correctly classified as
  `dependency-setup-blocker`, which turns the amos-saas failure from a noisy
  command failure into actionable dependency setup evidence.
- Google Fonts/`next/font` and `uv` cache failures are now grouped under
  environment or runner blockers in completed verification artifacts.
- `refresh` needs a workflow-level timeout and partial-result finalization.
  Tenure and BidCamp hung after run artifacts were written but before verify
  artifacts and final JSON existed, forcing manual interruption.
- Nested package-manager handling improved enough to surface more explicit
  evidence, but Dsci-proj still shows npm command discovery in a nested
  dashboard, so package-manager normalization should rewrite discovered nested
  npm scripts to the repo's configured/lockfile-backed manager where possible.
- The controller report protocol is working: every worker produced an accepted
  completion report, even when the QR workflow itself hung or failed.

## Product Fixes Before Refresh Wave 3

Refresh wave 2 exposed the next Tier 1 blocker: `quality-runner refresh` could
hang during `verify-gates` after writing inspect/run artifacts but before
writing verify artifacts or final JSON.

Implemented refresh hardening:

- `refresh` now has an overall verify-phase workflow timeout in addition to
  per-gate timeouts.
- Timeout payloads always include an explicit reason, phase, configured timeout,
  elapsed time, and `workflow-timeout` failure type.
- If verify times out, QR writes partial but valid verify artifacts:
  `gate-execution-plan.json`, `gate-verification.json`,
  `workflow-timeout.json`, `run-manifest.json`, and `run-summary.json`.
- Run summaries classify this state as `workflow-timeout-blocker`, so
  controllers do not confuse it with repo-owned failing gates or dependency
  setup blockers.
- CLI callers can set `--workflow-timeout-seconds` and
  `--workflow-timeout-reason`; the next rerun uses an explicit controller
  reason.

Validation before launch: `uv run ruff check .`, targeted workflow/CLI/artifact
tests, and full `uv run pytest` all pass on controller commit `8b27624`.

## Refresh Wave 3 Results

Refresh wave 3 reran the same five triage repos in read-only mode with
`--workflow-timeout-seconds 180` and the explicit reason
`controller refresh wave 3 verify deadline after wave 2 empty verify artifacts`.
All five worker reports validated against
`quality-runner-controller-report-validation-v0.1`.

| Repo | Thread id | Report | Final status | Timeout reason captured | Result |
|---|---|---|---|---|---|
| tenure | `019f2676-1575-7e12-add9-8865f919cfbb` | `/private/tmp/qr-refresh3-tenure-report.json` | blocked; `workflow-timeout-blocker` | yes; `workflow-timeout.json` elapsed 180.022s | QR wrote `gate-execution-plan.json`, `gate-verification.json`, `workflow-timeout.json`, `run-manifest.json`, and `run-summary.json` instead of leaving an empty verify directory. |
| BidCamp | `019f2676-51f1-77e1-8d81-077f48dbc989` | `/private/tmp/qr-refresh3-BidCamp-report.json` | blocked; `workflow-timeout-blocker` | yes; `workflow-timeout.json` elapsed 180.016s | QR finalized partial verify artifacts with the delegated controller reason; pre-existing tracked local edits remained untouched. |
| AIOS | `019f2676-8a20-7ad1-93e9-c94a7bcb7d39` | `/private/tmp/qr-refresh3-AIOS-report.json` | blocked; `environment-or-runner-blocker` | not applicable | Normal verify artifacts were written. Failures were existing formatter/lint/typecheck debt plus runner-environment failures for `uv` cache access and offline font/build behavior. |
| amos-saas | `019f2676-c290-75b3-a889-dd39f343bcd8` | `/private/tmp/qr-refresh3-amos-saas-report.json` | blocked; `environment-or-dependency-blocker` | not applicable | Normal verify artifacts were written. Gates remain blocked by `pnpm install` aborting non-interactively while removing `node_modules`; mutating gates stayed skipped under read-only policy. |
| Dsci-proj | `019f2677-0c4e-7c22-983e-8ff4a1d6f7e4` | `/private/tmp/qr-refresh3-Dsci-proj-report.json` | failed; `failing-executable-gates` | not applicable | Normal verify artifacts were written. `runtime_smoke` passed, while formatter, lint, typecheck, tests, build, and dead-code failed on repo-owned executable-gate debt. |

Product outcome:

- The timeout reason is now first-class evidence. Timed-out refreshes include
  the controller-supplied reason in `gate-verification.json`,
  `workflow-timeout.json`, and the final summary classification.
- The empty verify-directory failure mode is fixed for the observed Tenure and
  BidCamp cases. Controllers now receive a blocked QR run with valid final
  artifacts and can advance waves without manual reconstruction.
- The remaining Tier 1 gap is deadline enforcement against child process trees.
  The signal-based workflow timeout finalizes artifacts with the correct
  elapsed timeout, but QR should supervise verify work in a process group and
  terminate descendants so a stuck package command cannot delay return or keep
  consuming resources after the workflow deadline.
- Read-only reruns preserved target worktrees: QR generated only untracked
  `.quality-runner/` artifacts, and the reports clearly separated pre-existing
  local edits from QR output.

## Product Fixes Before Refresh Wave 4

Refresh wave 3 also clarified that timeout finalization is only the fallback.
The primary Tier 1 path is making more QR runs complete inside the delegated
deadline.

Implemented refresh efficiency hardening:

- Gate execution now uses a cost-aware order. Cheap/high-signal executable
  gates run before expensive `tests`, `build`, `pre_cr`, and `pre_pr` gates,
  while the written `gate-execution-plan.json` matches the actual execution
  order.
- `verify-gates` writes `gate-execution-plan.json` before executing gates and
  refreshes `gate-verification.json` after each gate result. If a later gate
  stalls, the controller still receives completed-gate evidence rather than an
  all-or-nothing artifact.
- Structural scans now have a configurable text-file budget through
  `quality_runner.structural_scan.max_text_files`; the default is 2,500 files.
  When the cap is reached, skipped files and directories are recorded with
  `scan budget exceeded` evidence and a `summary.scan_budget` payload.

Validation before launch: `uv run ruff check .` and full `uv run pytest`
passed for controller commit `614baa2`.

## Refresh Wave 4 Launch

Refresh wave 4 is a regression/stress wave over the same five repos from wave
3. The goal is to test whether efficiency hardening makes runs more complete
inside the deadline, not to remediate target repos.

Shared command shape:

- `--timeout-seconds 90`
- `--workflow-timeout-seconds 180`
- `--workflow-timeout-reason "controller refresh wave 4 efficiency regression
  deadline after gate-ordering scan-budget partial-artifact hardening"`
- no `--allow-mutating-gates`

| Repo | Thread id | Run id prefix | Baseline | Report path | Status |
|---|---|---|---|---|---|
| tenure | `019f285c-d4d1-7083-87b1-be762fcea99b` | `refresh4-20260703-tenure` | `refresh3-20260703-tenure-verify` | `/private/tmp/qr-refresh4-tenure-report.json` | launched |
| BidCamp | `019f285d-2584-7f21-8b2b-8c24aaa281a3` | `refresh4-20260703-BidCamp` | `refresh3-20260703-BidCamp-verify` | `/private/tmp/qr-refresh4-BidCamp-report.json` | launched |
| AIOS | `019f285d-5f64-7713-9e69-593bfaf4d02b` | `refresh4-20260703-AIOS` | `refresh3-20260703-AIOS-verify` | `/private/tmp/qr-refresh4-AIOS-report.json` | launched |
| amos-saas | `019f285d-ae2a-7822-8df0-9da2cbfe3d65` | `refresh4-20260703-amos-saas` | `refresh3-20260703-amos-saas-verify` | `/private/tmp/qr-refresh4-amos-saas-report.json` | launched |
| Dsci-proj | `019f285e-19cc-7f41-baa5-03cacecb7c36` | `refresh4-20260703-Dsci-proj` | `refresh3-20260703-Dsci-proj-verify` | `/private/tmp/qr-refresh4-Dsci-proj-report.json` | launched |

## Refresh Wave 4 Results

All five wave-4 worker reports validated against
`quality-runner-controller-report-validation-v0.1`.

| Repo | Report status | Final QR status | Scan budget | Timeout | Key result |
|---|---|---|---|---|---|
| tenure | blocked | blocked; `workflow-timeout-blocker` | 751 / 2,500 scanned; no budget skip | yes; explicit reason | Mid-run `gate-execution-plan.json` and `gate-verification.json` held useful gate evidence, but timeout finalization overwrote both to empty terminal artifacts. |
| BidCamp | blocked | blocked; `workflow-timeout-blocker` | 2,205 / 2,500 scanned; no budget skip | yes; explicit reason | Mid-run verification accumulated `formatter` skipped and `lint` passed, but final timeout artifacts dropped the plan and completed gate evidence. |
| AIOS | blocked | blocked; `environment-or-runner-blocker` | 742 / 2,500 scanned; no budget skip | no | Refresh completed normal verification with usable final artifacts; remaining blockers are repo/environment gate failures. |
| amos-saas | blocked | blocked; `workflow-timeout-blocker` | 241 / 2,500 scanned; no budget skip | yes; explicit reason | Static scan stayed efficient, but verify hit the workflow timeout before a non-empty gate plan or completed gate evidence survived. |
| Dsci-proj | ready-for-review | failed; `failing-executable-gates` | 198 / 2,500 scanned; no budget skip | no | Efficiency hardening worked: final artifacts retained gate evidence, and failure was existing repo-owned executable gate debt. |

Wave-4 product findings:

- Scan-budget hardening is working across the regression set. All five repos
  stayed under the default 2,500 text-file budget, and none produced
  `scan budget exceeded` skipped evidence.
- Partial gate artifacts now exist during long-running verification. Tenure and
  BidCamp both exposed mid-run `gate-verification.json` evidence while the
  parent refresh was still active.
- Timeout finalization is now the blocker: when the workflow timeout fires, QR
  rebuilds terminal `gate-execution-plan.json` and `gate-verification.json` as
  empty artifacts, discarding the useful partial evidence.
- The process-tree deadline issue remains. Tenure and BidCamp workers observed
  the parent refresh running beyond the configured 180-second workflow deadline
  before returning a timeout result.

## Product Fixes Before Refresh Wave 5

Refresh wave 4 showed that the new partial verification artifacts were useful
during execution, but timeout finalization erased them. Wave 5 should verify
that timeout artifacts now preserve completed gate evidence and that interrupted
gate processes are cleaned up promptly.

Implemented timeout hardening:

- Workflow timeout finalization now preserves an existing
  `gate-execution-plan.json` instead of replacing it with an empty array.
- Workflow timeout finalization now merges timeout metadata into an existing
  `gate-verification.json` while retaining any completed gate results.
- Gate execution now launches shell commands in their own process group and
  terminates that process group if a per-gate timeout or workflow-level
  interruption occurs.

Validation before launch: `uv run ruff check .` and full `uv run pytest`
passed for controller commit `225dab2`.

## Refresh Wave 5 Launch

Refresh wave 5 reruns the same five repos to verify timeout evidence
preservation and process-group cleanup after controller commit `6be4dc2`.

Shared command shape:

- `--timeout-seconds 90`
- `--workflow-timeout-seconds 180`
- `--workflow-timeout-reason "controller refresh wave 5 timeout preservation
  process-group cleanup regression"`
- no `--allow-mutating-gates`

| Repo | Thread id | Run id prefix | Baseline | Report path | Status |
|---|---|---|---|---|---|
| tenure | `019f286e-e00b-75f1-a8a5-3aa66deb9123` | `refresh5-20260703-tenure` | `refresh4-20260703-tenure-verify` | `/private/tmp/qr-refresh5-tenure-report.json` | launched |
| BidCamp | `019f286f-2247-7120-9224-b4128761a293` | `refresh5-20260703-BidCamp` | `refresh4-20260703-BidCamp-verify` | `/private/tmp/qr-refresh5-BidCamp-report.json` | launched |
| AIOS | `019f286f-61b3-7141-9f84-91aeb7b10134` | `refresh5-20260703-AIOS` | `refresh4-20260703-AIOS-verify` | `/private/tmp/qr-refresh5-AIOS-report.json` | launched |
| amos-saas | `019f286f-9d40-76f1-9b18-ded4fce2bfe1` | `refresh5-20260703-amos-saas` | `refresh4-20260703-amos-saas-verify` | `/private/tmp/qr-refresh5-amos-saas-report.json` | launched |
| Dsci-proj | `019f286f-dd9b-7f03-82d8-d83cdd3306d4` | `refresh5-20260703-Dsci-proj` | `refresh4-20260703-Dsci-proj-verify` | `/private/tmp/qr-refresh5-Dsci-proj-report.json` | launched |

## Refresh Wave 5 Results

All five worker reports validated with
`quality-runner validate-report <report> --json` and returned
`status=accepted`, `errors=[]`.

| Repo | Thread status | Final QR run/status | Timeout path | Final artifacts | Command elapsed | Report |
|---|---|---|---|---|---:|---|
| tenure | blocked | `refresh5-20260703-tenure-verify` / `workflow-timeout-blocker` | exercised; reason preserved; verify elapsed `180.134s` | preserved 9 planned gates and 4 recorded gate outcomes after timeout | `410s` | `/private/tmp/qr-refresh5-tenure-report.json` |
| BidCamp | blocked | `refresh5-20260703-BidCamp-verify` / `workflow-timeout-blocker` | exercised; reason preserved; verify elapsed `180.223s` | preserved 10 planned gates and 4 recorded gate outcomes after timeout | `384s` | `/private/tmp/qr-refresh5-BidCamp-report.json` |
| AIOS | blocked | `refresh5-20260703-AIOS-verify` / `environment-or-runner-blocker` | not exercised; completed before 180s | preserved final 10-gate plan and 10 gate outcomes | `157.13s` | `/private/tmp/qr-refresh5-AIOS-report.json` |
| amos-saas | blocked | `refresh5-20260703-amos-saas-verify` / `environment-or-dependency-blocker` | not exercised; completed before 180s | preserved final 9-gate plan and 9 gate outcomes | `80s` | `/private/tmp/qr-refresh5-amos-saas-report.json` |
| Dsci-proj | ready-for-review | `refresh5-20260703-Dsci-proj-verify` / `failing-executable-gates` | not exercised; completed before 180s | preserved final 10-gate plan and 10 gate outcomes | `48.54s` | `/private/tmp/qr-refresh5-Dsci-proj-report.json` |

Product takeaways:

- Timeout finalization no longer destroys useful verify evidence. Tenure and
  BidCamp both wrote `workflow-timeout.json` with the explicit controller
  reason and preserved non-empty `gate-execution-plan.json` and
  `gate-verification.json` after timing out.
- Process-group cleanup at the individual gate command layer was not enough to
  make the full refresh invocation return near the requested 180-second
  deadline. Tenure took about `410s` and BidCamp took about `384s` end to end
  because inspect/run phases occurred before the verify-phase timeout window.
- The next Tier 1 hardening target is a top-level refresh deadline that spans
  inspect, audit run, and verify, with phase-level timing in the final JSON so
  controllers can distinguish scan cost from gate execution cost.
- The non-timeout repos still provided useful regression evidence: final verify
  artifacts were populated and scan budgets avoided dependency/generated path
  explosions.

## Product Fix After Refresh Wave 5

Implemented explicit refresh timeout scopes after the wave 5 timing ambiguity:

- `--verify-timeout-seconds` now names the verify-gates phase timeout directly.
- `--workflow-timeout-seconds` remains as a backward-compatible alias for the
  verify timeout.
- `--total-timeout-seconds` adds an optional full-refresh deadline across
  inspect, run, and verify for controller wave budgets.
- Refresh JSON now includes `timeout_contract` and `phase_timings`, making it
  clear whether a long run was allowed to gather full evidence or was expected
  to obey a hard end-to-end deadline.

Validation before the next wave: `uv run ruff check .`, `uv run pytest`, and
`git diff --check` passed locally.

## Refresh Wave 6 Launch

Refresh wave 6 reruns the same five repos in two modes to verify the new timeout
contract:

- Full-evidence mode: `--verify-timeout-seconds 180` and no
  `--total-timeout-seconds`.
- Controller-budget mode: `--verify-timeout-seconds 180`,
  `--total-timeout-seconds 240`, and explicit total timeout reason
  `controller refresh wave 6 total budget`.

Each worker must compare `timeout_contract`, `phase_timings`, timeout artifact
phase/reason, artifact preservation, scan budget, and target git status across
both modes.

| Repo | Thread id | Full run id prefix | Budget run id prefix | Baseline | Report path | Status |
|---|---|---|---|---|---|---|
| tenure | `019f2888-965b-7080-8b5a-d61122165ee3` | `refresh6full-20260703-tenure` | `refresh6budget-20260703-tenure` | `refresh5-20260703-tenure-verify` | `/private/tmp/qr-refresh6-tenure-report.json` | launched |
| BidCamp | `019f2888-d027-78d1-8a23-bcaea6cea3a3` | `refresh6full-20260703-BidCamp` | `refresh6budget-20260703-BidCamp` | `refresh5-20260703-BidCamp-verify` | `/private/tmp/qr-refresh6-BidCamp-report.json` | launched |
| AIOS | `019f2889-1688-7f93-be30-1cd44e4026ee` | `refresh6full-20260703-AIOS` | `refresh6budget-20260703-AIOS` | `refresh5-20260703-AIOS-verify` | `/private/tmp/qr-refresh6-AIOS-report.json` | launched |
| amos-saas | `019f2889-510f-7882-9f6a-f5b58a1174c0` | `refresh6full-20260703-amos-saas` | `refresh6budget-20260703-amos-saas` | `refresh5-20260703-amos-saas-verify` | `/private/tmp/qr-refresh6-amos-saas-report.json` | launched |
| Dsci-proj | `019f2889-8e89-7472-a39f-d4c7ed7b4c1c` | `refresh6full-20260703-Dsci-proj` | `refresh6budget-20260703-Dsci-proj` | `refresh5-20260703-Dsci-proj-verify` | `/private/tmp/qr-refresh6-Dsci-proj-report.json` | launched |

## Refresh Wave 6 Results

All five worker reports validated with
`quality-runner validate-report <report> --json` and returned
`status=accepted`, `errors=[]`.

| Repo | Thread status | Full-evidence result | Budget result | Contract signal | Report |
|---|---|---|---|---|---|
| tenure | blocked | `361.73s`; `workflow-timeout-blocker`; verify timeout reason | `240.36s`; `workflow-timeout-blocker`; total-budget reason | Full mode omitted total timeout; budget mode stopped at the 240s controller budget and preserved partial gate evidence. | `/private/tmp/qr-refresh6-tenure-report.json` |
| BidCamp | blocked | `341s`; `workflow-timeout-blocker`; 6 gate results | `240s`; `workflow-timeout-blocker`; 5 gate results | Budget mode stopped at the controller budget and captured less gate evidence by design. | `/private/tmp/qr-refresh6-BidCamp-report.json` |
| AIOS | ready-for-review | `135.09s`; `environment-or-runner-blocker`; no timeout | `112.72s`; `environment-or-runner-blocker`; no timeout | Budget contract was present in JSON but did not fire because the run completed before 240s. | `/private/tmp/qr-refresh6-AIOS-report.json` |
| amos-saas | ready-for-review | `56.24s`; `environment-or-dependency-blocker`; no timeout | `43.31s`; `environment-or-dependency-blocker`; no timeout | Both modes completed before timeout; dependency setup blocker remained the actual result. | `/private/tmp/qr-refresh6-amos-saas-report.json` |
| Dsci-proj | ready-for-review | `34.71s`; `failing-executable-gates`; no timeout | `30.86s`; `failing-executable-gates`; no timeout | Both modes completed before timeout; executable gate failures remained the actual result. | `/private/tmp/qr-refresh6-Dsci-proj-report.json` |

Product takeaways:

- The timeout contract split worked. Full-evidence mode now clearly reports no
  total timeout in `timeout_contract`, while budget mode carries
  `total_timeout_seconds=240` and the explicit controller reason.
- The optional total budget did what controller waves need on the long-running
  repos: Tenure and BidCamp returned near 240 seconds instead of running 340+
  seconds, while preserving non-empty gate plans and partial gate verification
  evidence.
- The user-facing product choice is now defensible: default/no-total-timeout
  collects more evidence; controller-budget mode trades some late-gate evidence
  for predictable wall time.
- Remaining polish: timeout artifacts still report the active phase as
  `verify-gates` even when the deadline source is the total refresh budget.
  The artifact should add an explicit `deadline_scope` or `timeout_scope` field
  (`verify-phase` vs `total-refresh`) so controllers do not infer scope from
  the reason string.

## Product Fix After Refresh Wave 6

Implemented timeout scope evidence:

- Timeout artifacts now include `timeout_scope`.
- `gate-verification.json` timeout finalization also includes `timeout_scope`.
- Values are `verify-phase` for verify-only deadlines and `total-refresh` for
  full refresh budget deadlines, even when the active phase remains
  `verify-gates`.
- The CLI docs now describe the field for controller consumers.

## Refresh Wave 7 Launch

Refresh wave 7 is a focused two-repo verification after adding
`timeout_scope`:

- Tenure checks both timeout scopes: full-evidence verify timeout should emit
  `timeout_scope=verify-phase`; controller-budget timeout should emit
  `timeout_scope=total-refresh`.
- AIOS checks the non-timeout path: budget contract and phase timings should
  remain present while no timeout artifact is written.

| Repo | Thread id | Run id prefix | Baseline | Report path | Status |
|---|---|---|---|---|---|
| tenure | `019f28ac-2a8e-7260-8290-c43dfeb4f79b` | `refresh7full-20260703-tenure`, `refresh7budget-20260703-tenure` | `refresh6full-20260703-tenure-verify`, `refresh6budget-20260703-tenure-verify` | `/private/tmp/qr-refresh7-tenure-report.json` | launched |
| AIOS | `019f28ac-721a-7d03-a790-b2b03e484dfb` | `refresh7budget-20260703-AIOS` | `refresh6budget-20260703-AIOS-verify` | `/private/tmp/qr-refresh7-AIOS-report.json` | launched |

## Refresh Wave 7 Results

Both worker reports validated with
`quality-runner validate-report <report> --json` and returned
`status=accepted`, `errors=[]`.

| Repo | Thread status | Final QR result | Scope evidence | Report |
|---|---|---|---|---|
| tenure | blocked | Full mode `340.77s`; budget mode `240.67s`; both `workflow-timeout-blocker` | Full mode wrote `timeout_scope=verify-phase`; budget mode wrote `timeout_scope=total-refresh`; both preserved the 9-entry gate plan and gate verification evidence. | `/private/tmp/qr-refresh7-tenure-report.json` |
| AIOS | ready-for-review | `120.38s`; `environment-or-runner-blocker`; no workflow timeout | Non-timeout refresh retained `timeout_contract` and `phase_timings`, wrote no `workflow-timeout.json`, and had no timeout-scope artifact fields. | `/private/tmp/qr-refresh7-AIOS-report.json` |

Product takeaways:

- The timeout-scope polish is verified. Controllers no longer need to parse
  timeout reason strings to distinguish verify-phase budget exhaustion from
  total-refresh budget exhaustion.
- Non-timeout runs remain cleanly modeled: they expose the selected timeout
  contract and phase timings, but do not fabricate timeout-scope artifacts.
- Timeout work is now complete enough to stop focused timeout waves. The next
  Tier 1 product gap is dependency/setup blocker handling, especially repeated
  non-interactive `pnpm` dependency restoration failures.

## Product Fix After Refresh Wave 7

Implemented dependency setup blocker short-circuiting:

- Gate verification now remembers the first `dependency-setup-blocker` for each
  package-manager/cwd context.
- Later gates in the same context are skipped as
  `skip_type=dependency-setup-blocked` with `blocked_by` pointing at the first
  failed gate.
- Failed and skipped dependency setup gates now include
  `diagnostics.dependency_setup` with package manager, cwd, recommended setup
  command, and cause.
- This keeps amos-saas-style non-interactive `pnpm` restoration failures
  actionable without repeatedly spawning gates that cannot pass until
  dependency setup is repaired.

Validation:

- `uv run pytest tests/test_workflow_gate_preflight.py -k dependency_setup_blockers`
- `uv run pytest tests/test_workflow_gate_preflight.py tests/test_config.py tests/test_workflow.py`
- `uv run ruff check .`

## Refresh Wave 8 Launch

Refresh wave 8 validates the dependency setup blocker short-circuit against two
dependency/setup candidates and one clean control repo:

- `amos-saas` checks the known non-interactive `pnpm` restoration path. Expected
  evidence is one root `dependency-setup-blocker` per package-manager/cwd
  context, later same-context gates skipped with
  `skip_type=dependency-setup-blocked`, `blocked_by`, and
  `diagnostics.dependency_setup`.
- `EliHealth` checks a second dependency/setup-heavy repo and records whether
  the new behavior appears or whether current failures are unrelated.
- `R-Project` is the control path. Expected evidence is no dependency setup
  blocker fields and no regression in the non-JS clean/control path.

| Repo | Thread id | Run id prefix | Baseline | Report path | Status |
|---|---|---|---|---|---|
| amos-saas | `019f28c5-c1f0-7740-9d39-691fbb2d2cbc` | `refresh8-20260703-amos-saas` | `refresh6budget-20260703-amos-saas-verify` | `/private/tmp/qr-refresh8-amos-saas-report.json` | accepted |
| EliHealth | `019f28c5-c7e7-7991-bb99-098df638dbd9` | `refresh8-20260703-EliHealth` | `triage-20260702-EliHealth` | `/private/tmp/qr-refresh8-EliHealth-report.json` | accepted |
| R-Project | `019f28c5-d50d-7540-aa89-1d7e325151a4`; superseded locally | `refresh8-20260703-R-Project` | `stress-20260703-R-Project-final-verify` | `/private/tmp/qr-refresh8-R-Project-report.json` | accepted |

## Refresh Wave 8 Results

All three reports validated with
`quality-runner validate-report <report> --json` and returned
`status=accepted`, `errors=[]`.

| Repo | Thread status | Final QR result | Dependency setup evidence | Report |
|---|---|---|---|---|
| amos-saas | blocked | `environment-or-dependency-blocker`; final verify `blocked` | Product fix verified. `lint` was the sole root `dependency-setup-blocker`; `typecheck`, `runtime_smoke`, `dead_code`, `tests`, `build`, and `pre_cr` skipped with `skip_type=dependency-setup-blocked`, `blocked_by=lint`, and `diagnostics.dependency_setup` including `pnpm install --frozen-lockfile`. | `/private/tmp/qr-refresh8-amos-saas-report.json` |
| EliHealth | blocked | `read-only-gate-blocker`; final verify `blocked` | New product gap found. Repeated `ERR_PNPM_IGNORED_BUILDS` setup failures remained `command-failed`; QR emitted no dependency setup diagnostics and did not skip later same-context gates. Build also had an unrelated missing `vite/client` type failure. | `/private/tmp/qr-refresh8-EliHealth-report.json` |
| R-Project | ready-for-review | `clean`; final verify `passed` | Control path passed. No `dependency-setup-blocker`, no `dependency-setup-blocked` skips, `tests` passed, and `pre_cr` skipped without dependency setup diagnostics. | `/private/tmp/qr-refresh8-R-Project-report.json` |

Product takeaways:

- The short-circuit fix works for the known amos-saas non-interactive pnpm
  dependency restoration case and removes repeated noisy gate failures.
- The next dependency setup classifier must cover pnpm ignored-build approval
  failures (`ERR_PNPM_IGNORED_BUILDS`) and recommend `pnpm approve-builds`
  before rerunning gates.
- Once that classifier is added, the same same-context skip behavior should
  apply so EliHealth-style runs produce one actionable dependency setup blocker
  instead of seven repeated command failures.
- The R-Project control run confirms the new dependency setup memory does not
  disturb clean non-JS verification.

## Product Fix After Refresh Wave 8

Implemented pnpm ignored-build dependency setup handling:

- `ERR_PNPM_IGNORED_BUILDS`, `Ignored build scripts`, and
  `pnpm approve-builds` output now classify as `dependency-setup-blocker`.
- Dependency setup diagnostics now point pnpm ignored-build failures at
  `pnpm approve-builds` instead of the generic install command.
- Later same package-manager/cwd gates reuse the root setup diagnostic when
  skipped with `skip_type=dependency-setup-blocked`, so downstream gates retain
  the specific approval command.

Validation:

- `uv run pytest tests/test_workflow_gate_preflight.py -k 'dependency_setup or pnpm_ignored_builds'`
- `uv run pytest tests/test_workflow_gate_preflight.py tests/test_config.py tests/test_workflow.py`
- `uv run ruff check .`

## Refresh Wave 9 EliHealth Canary

Ran a focused read-only EliHealth canary after adding pnpm ignored-build
classification:

- Run id prefix: `refresh9-20260703-EliHealth`
- Baseline: `refresh8-20260703-EliHealth-verify`
- Final verify: `refresh9-20260703-EliHealth-verify`
- Final classification: `environment-or-dependency-blocker`
- Result: `lint` became the root `dependency-setup-blocker` with
  `diagnostics.dependency_setup.setup_command=pnpm approve-builds`.
- Same-context pnpm gates `typecheck`, `runtime_smoke`, `dead_code`, `tests`,
  `pre_cr`, and `pre_pr` skipped with `skip_type=dependency-setup-blocked`,
  `blocked_by=lint`, and the same `pnpm approve-builds` diagnostic.
- The unrelated `build` gate still failed as `command-failed` because `web`
  is missing the `vite/client` type definition.

Validation:

- `uv run quality-runner refresh /Users/jakyeamos/projects/EliHealth --run-id-prefix refresh9-20260703-EliHealth --baseline-run-id refresh8-20260703-EliHealth-verify --timeout-seconds 90 --verify-timeout-seconds 180 --total-timeout-seconds 240 --total-timeout-reason "controller refresh wave 9 pnpm ignored builds validation" --json`
- `jq '.gates | map({id,status,failure_type,skip_type,blocked_by,setup:(.diagnostics.dependency_setup // null), recommended_action})' /Users/jakyeamos/projects/EliHealth/.quality-runner/runs/refresh9-20260703-EliHealth-verify/gate-verification.json`
- `uv run pytest`
- `uv run ruff check .`

## Refresh Wave 10 Classification Consistency

Refresh wave 10 compared `gate-verification.json`, `run-summary.json`,
`quality-runner status --json`, controller report validation, and handoff
artifacts across two dependency setup repos, one clean control, and one
failing-executable-gates control.

All four reports validated with
`quality-runner validate-report <report> --json` and returned
`status=accepted`, `errors=[]`.

| Repo | Final QR result | Status JSON | Handoff result | Report |
|---|---|---|---|---|
| EliHealth | `blocked`; `environment-or-dependency-blocker`; root `lint` dependency setup blocker; same-context pnpm gates skipped with `blocked_by=lint` and `pnpm approve-builds` diagnostics | `status=blocked`; latest verify `refresh10-20260703-EliHealth-verify` | inconsistent: `Status: gates-executed`, no final classification, no dependency setup blocker, structural next slice shown first | `/private/tmp/qr-refresh10-EliHealth-report.json` |
| amos-saas | `blocked`; `environment-or-dependency-blocker`; root `lint` dependency setup blocker; same-context pnpm gates skipped with `blocked_by=lint` and `pnpm install --frozen-lockfile` diagnostics | `status=blocked`; latest verify `refresh10-20260703-amos-saas-verify` | inconsistent: `Status: gates-executed`, no final classification, no dependency setup blocker, structural next slice shown first | `/private/tmp/qr-refresh10-amos-saas-report.json` |
| R-Project | `passed`; `clean`; tests passed and aggregate pre-CR skipped | `status=ready`; latest verify `refresh10-20260703-R-Project-verify` | consistent: `Status: gates-clean` and clean baseline next slice | `/private/tmp/qr-refresh10-R-Project-report.json` |
| AIOS | `failed`; `failing-executable-gates`; formatter/lint/typecheck/build failed as command failures, runtime smoke/dead-code/tests passed | `status=blocked`; latest verify `refresh10-20260703-AIOS-verify` | inconsistent: `Status: gates-executed`, no final classification, failed executable gates not shown first, structural next slice shown first | `/private/tmp/qr-refresh10-AIOS-report.json` |

Product takeaways:

- `gate-verification.json`, `run-summary.json`, `quality-runner status --json`,
  and controller report validation are now consistent for clean, dependency
  setup, and failing executable gate outcomes.
- The remaining Tier 1 consistency gap is handoff generation. Blocked/failed
  verify runs still emit `Status: gates-executed` and prioritize structural
  remediation, even when the real stopping point is dependency setup or failed
  executable gates.
- Next product fix: include final gate verification status, recommended
  classification, failed/blocked gate summary, dependency setup diagnostics,
  and recommended setup command in `agent-handoff.json` and
  `agent-handoff.md`; for blocked/failed gates, handoff should make the gate
  blocker the next slice before broad structural debt.

Follow-up implementation:

- `agent-handoff.json` now includes a `gate_verification` summary for verified
  runs with final status, recommended classification, and failed/blocked gate
  blockers.
- Blocked and failed verification runs now use explicit `gates-blocked` and
  `gates-failed` handoff statuses instead of generic `gates-executed`.
- Blocked and failed verification runs now queue
  `resolve-gate-verification-blockers` as the next slice before structural debt,
  carrying dependency setup commands such as `pnpm approve-builds` into both
  JSON and Markdown handoffs.

## Refresh Wave 11 Launch

Wave 11 validates the handoff fix from commit `f84d51c` across the dependency
setup cases, failed executable gate case, clean control, and QR-spawned
test/environment stress case. Each thread must report back with final QR status,
handoff status, classification, blocker-first next-slice verdict, controller
report validation, files changed, and blockers.

| Repo | Thread id | Run id prefix | Baseline | Report path | Status |
|---|---|---|---|---|---|
| EliHealth | `019f28f5-6060-7352-a133-80d24d42ebef` | `refresh11-20260703-EliHealth` | `refresh10-20260703-EliHealth-verify` | `/private/tmp/qr-refresh11-EliHealth-report.json` | launched |
| amos-saas | `019f28f5-711f-7362-88e6-0280959e5aee` | `refresh11-20260703-amos-saas` | `refresh10-20260703-amos-saas-verify` | `/private/tmp/qr-refresh11-amos-saas-report.json` | launched |
| AIOS | `019f28f5-9852-7372-a815-7706042bb41e` | `refresh11-20260703-AIOS` | `refresh10-20260703-AIOS-verify` | `/private/tmp/qr-refresh11-AIOS-report.json` | launched |
| R-Project | `019f28f5-a62a-7e31-bf29-bc01c3dd1145` | `refresh11-20260703-R-Project` | `refresh10-20260703-R-Project-verify` | `/private/tmp/qr-refresh11-R-Project-report.json` | launched |
| BIP-Console | `019f28f5-b3b7-7c31-abf4-1f6089eeec94` | `refresh11-20260703-BIP-Console` | `canary-20260703-BIP-Console-classifier-fix-verify`, fallback `stress-20260703-BIP-Console-final2-verify` | `/private/tmp/qr-refresh11-BIP-Console-report.json` | launched |

## Refresh Wave 11 Results

All five Wave 11 reports validated with
`quality-runner validate-report <report> --json` and returned
`status=accepted`, `errors=[]`.

| Repo | Final QR result | Handoff result | Consistency verdict | Report |
|---|---|---|---|---|
| EliHealth | `blocked`; `environment-or-dependency-blocker`; 24 findings, delta 0 | `gates-blocked`; dependency setup blockers include `pnpm approve-builds`; next slice `resolve-gate-verification-blockers` | consistent | `/private/tmp/qr-refresh11-EliHealth-report.json` |
| amos-saas | `blocked`; `environment-or-dependency-blocker`; 27 findings, delta 0 | `gates-blocked`; dependency setup blockers include `pnpm install --frozen-lockfile`; next slice `resolve-gate-verification-blockers` | pass | `/private/tmp/qr-refresh11-amos-saas-report.json` |
| AIOS | `failed`; `failing-executable-gates`; 22 findings, delta 0 | `gates-failed`; failed formatter/lint/typecheck blockers; next slice `resolve-gate-verification-blockers` | passed | `/private/tmp/qr-refresh11-AIOS-report.json` |
| R-Project | `passed`; `clean`; 0 findings | `gates-clean`; `next_slice=null`; no blockers; status JSON `ready` | consistent | `/private/tmp/qr-refresh11-R-Project-report.json` |
| BIP-Console | `blocked`; `read-only-gate-blocker`; 10 findings, delta 0 | `gates-blocked`; formatter skipped as `mutating-gate-not-run`; next slice `resolve-gate-verification-blockers`; all non-mutating executable gates passed | consistent | `/private/tmp/qr-refresh11-BIP-Console-report.json` |

Product takeaways:

- The handoff fix is validated. Blocked dependency/setup runs now say
  `gates-blocked`, failed executable-gate runs say `gates-failed`, and clean
  runs still say `gates-clean`.
- `agent-handoff.json` and `.md` now expose the final gate classification,
  blocker list, setup commands, and gate-blocker next slice before structural
  remediation across all tested states.
- Next Tier 1 gap: read-only verification can still mutate tracked repo files
  through non-mutating-looking commands. AIOS gate execution regenerated tracked
  log files and the worker restored the pre-refresh patch manually. QR should
  detect and report post-gate tracked mutations, and ideally run verification in
  an isolated worktree or restore/snapshot tracked files when `--read-only-gates`
  is active.
- Handoff blocker ordering is correct but still coarse for mixed-blocker cases.
  EliHealth grouped read-only formatter skip, dependency setup blockers, and a
  command-failed build in one gate-blocker slice. The next polish is to mark a
  primary blocker class and group actions by dependency setup, read-only policy,
  command failures, and structural debt.
- BIP-Console no longer reproduced the earlier QR-spawned test timeout: tests
  passed in the refresh, and the only blocker was read-only formatter policy.

## Rollout Ledger

| Wave | Repo | Repo path | Total | Blockers | Baseline artifacts | Codex project status | Thread status | Thread id | Final QR status | Commit | Push | Notes |
|---:|---|---|---:|---:|---|---|---|---|---|---|---|---|
| 1 | tenure | `/Users/jakyeamos/projects/tenure` | 45 | 4 | `/Users/jakyeamos/projects/tenure/.quality-runner/runs/parallel-20260702T200935Z-tenure` | parent-project | blocked | `019f24fa-9946-7983-95be-33d1326f49ac` | findings; `wave1-restart-20260702-tenure-targeted`; no missing capabilities | `b464119d` | pushed | Targeted restart removed four findings, but final QR still had 3,678 structural instances; broad remaining buckets include nested ternary, spacing/design-token issues, deep nesting, explicit `any`, console output, and error-envelope consistency. |
| 1 | BidCamp | `/Users/jakyeamos/projects/BidCamp` | 39 | 2 | `/Users/jakyeamos/projects/BidCamp/.quality-runner/runs/parallel-20260702T200935Z-BidCamp` | exact-project | blocked | `019f24fa-d0d8-7821-a901-b186a39ecb15` | planned; `wave1-restart-20260702-BidCamp-2` | `60ffe151` | pushed | Fixed-runner restart added scoped QR config and image dimensions; `pnpm pre-cr` and dummy-env build passed. Blocked by 3,539 structural instances, 3,039 in `src`, requiring broad source refactor rather than scoped QR cleanup. |
| 1 | Vaults | `/Users/jakyeamos/projects/Vaults` | 39 | 5 | `/Users/jakyeamos/projects/Vaults/.quality-runner/runs/parallel-20260702T200935Z-Vaults` | parent-project | complete | `019f24fa-fe62-7f60-b832-798ee07f82bd` | clean | `2f19af9` | pushed | Restart verification clean with fixed runner: `wave1-restart-20260702-Vaults`; no new commit. |
| 1 | AIOS | `/Users/jakyeamos/projects/AIOS` | 34 | 1 | `/Users/jakyeamos/projects/AIOS/.quality-runner/runs/parallel-20260702T200935Z-AIOS` | parent-project | blocked | `019f24fb-3107-79a0-9af9-2a6de33f22ac` | planned; findings; no missing capabilities | `4031d38` | pushed | Restart run `wave1-restart-20260702-AIOS` with fixed QR runner dropped findings from 24,572 to 666; remaining blocker is broad repo-owned source debt. |
| 1 | amos-saas | `/Users/jakyeamos/projects/amos-saas` | 34 | 2 | `/Users/jakyeamos/projects/amos-saas/.quality-runner/runs/parallel-20260702T200935Z-amos-saas` | parent-project | blocked | `019f24fb-5f5d-7f91-bfb8-43e9f3744be4` | findings; `wave1-restart-20260702-amos-saas`; no missing capabilities | `7ad2690` | pushed | Restart produced no new commit; branch already pushed. Blocked by 27 grouped / 1,160 raw structural findings across 241 files, missing local env secrets, and dependency audit network policy. |
| 2 | Dsci-proj | `/Users/jakyeamos/projects/Dsci-proj` | 30 | 2 | `/Users/jakyeamos/projects/Dsci-proj/.quality-runner/runs/parallel-20260702T200935Z-Dsci-proj` | parent-project | complete | `019f2551-cb52-7e21-8270-b0cc8f4d3619` | planned; `triage-20260702-Dsci-proj`; no missing gates after scoped scripts | `3b95999`, `92bb60c` | pushed | Classification `broad-repo-debt`. Added dashboard `typecheck`, `audit:dead-code`, and `smoke` scripts plus source-only typecheck config and truth update. Smoke passed; exact TS gates expose existing dashboard dependency/type debt. Later QR rerun blocked by external runner `IndentationError` in `quality_runner/planning.py`. |
| 2 | Bballedu | `/Users/jakyeamos/projects/Bballedu` | 28 | 1 | `/Users/jakyeamos/projects/Bballedu/.quality-runner/runs/parallel-20260702T200935Z-Bballedu` | parent-project | complete | `019f2552-b117-78a0-9f9b-91d29db62d03` | planned; `triage-20260702-Bballedu`; no missing capabilities | `d422136`, `40968bf` | pushed | Classification `broad-repo-debt`. Added `.quality-runner.toml`, root `format` and `pre-pr` gates, and truth update. QR rerun completed with only broad structural findings; direct `pnpm format` execution was blocked by dependency restoration/build approval for `esbuild`. |
| 2 | BBDSE | `/Users/jakyeamos/projects/BBDSE` | 27 | 1 | `/Users/jakyeamos/projects/BBDSE/.quality-runner/runs/parallel-20260702T200935Z-BBDSE` | exact-project | blocked | `019f2552-b760-7b81-93f0-eefa2ecf4092` | blocked before artifact creation; `triage-20260702-BBDSE` stalled in traversal | `14a4f0e`, `e401994` | pushed | Classification `mixed-blocker`. Added QR config with generated/cache exclusions and existing gate evidence, plus truth update. QR status reads config, but fresh runs stalled before artifacts while traversing/statting repo surfaces; baseline still has missing `dead_code` and broad structural debt. |
| 2 | EliHealth | `/Users/jakyeamos/projects/EliHealth` | 27 | 2 | `/Users/jakyeamos/projects/EliHealth/.quality-runner/runs/parallel-20260702T200935Z-EliHealth` | exact-project | complete | `019f2552-c01f-7022-b78d-d07c0cc80255` | blocked-no-audit-artifacts; `triage-20260702-EliHealth` interrupted in `root.rglob(...)` discovery | `3914f35` | pushed | Classification `mixed-blocker`. Added canonical `format`, `typecheck`, and `smoke` scripts, converted tracked quality commands from `npm` to `pnpm`, and updated project truth. Underlying format/typecheck/smoke commands passed, but QR discovery traversed ignored dependency/build paths before artifacts and `pnpm` script execution was blocked by ignored native builds. |
| 2 | Fantasy | `/Users/jakyeamos/projects/Fantasy` | 27 | 4 | `/Users/jakyeamos/projects/Fantasy/.quality-runner/runs/parallel-20260702T200935Z-Fantasy` | exact-project | complete | `019f2552-ca61-7be2-9570-b6ecf5ff404c` | planned; findings; no missing repo-owned gates | `b50930deb0e1485d0ebd0183b60d57aaead5f3b4` | pushed | Classification `broad-repo-debt`. Added frontend quality gate scripts and truth update. QR rerun complete with `missing=[]`; `pnpm typecheck`, `pnpm audit:dead-code`, and `pnpm pre-pr` passed. `pnpm format` exposes existing 134-file formatting debt, so remaining work is broad backlog. |
| 3 | Book | `/Users/jakyeamos/projects/Book` | 22 | 4 | `/Users/jakyeamos/projects/Book/.quality-runner/runs/parallel-20260702T200935Z-Book` | exact-project | complete | `019f257a-efc4-7753-8982-69f7dec38242` | planned; `triage-20260702-Book`; no missing capabilities; 16 aggregate findings remain | `bcb466db7307e3dbe5cab367f47f5903205b1b3f` | pushed | Classification `broad-repo-debt`. Added top-level `format`, `lint`, `typecheck`, `audit:dead-code`, and `smoke` aliases plus truth update. All new gates and `pnpm test` passed; remaining broad buckets include simplify, UI structural, harden, deduplicate, speed, and ponytail. |
| 3 | dispatches-from-cyberspace | `/Users/jakyeamos/projects/dispatches-from-cyberspace` | 22 | 2 | `/Users/jakyeamos/projects/dispatches-from-cyberspace/.quality-runner/runs/parallel-20260702T200935Z-dispatches-from-cyberspace` | parent-project | complete | `019f257a-f6c5-7861-b89b-f6498d9a0278` | findings; `triage-20260702-dispatches-from-cyberspace`; no missing capabilities | `c3841a3` | pushed | Classification `broad-repo-debt`. Added `.gitignore`, `.prettierignore`, formatter/dead-code/pre-PR gates, pnpm build approval, lockfile changes, and truth update. QR now has zero missing gates; `format` and `audit:dead-code` execute and fail on existing formatting, parse, unused-file, dependency, and type debt. |
| 3 | remodelvision | `/Users/jakyeamos/projects/remodelvision` | 22 | 2 | `/Users/jakyeamos/projects/remodelvision/.quality-runner/runs/parallel-20260702T200935Z-remodelvision` | exact-project | blocked | `019f257b-026f-7c71-835f-f54516b69f79` | planned/findings; `triage-20260702-remodelvision`; missing gates cleared | not created | not pushed | Classification `env-or-dependency-blocker`. Added `format`, `smoke`, and `audit:dead-code` scripts in `package.json`, but the worker stopped after staging before commit/push. Verification was blocked by local `eslint-plugin-anti-slop` missing module, duplicate room-upload types, Prisma client runtime failure, and missing env vars; `.quality-runner/` remained untracked. |
| 3 | portfolio | `/Users/jakyeamos/projects/portfolio` | 20 | 2 | `/Users/jakyeamos/projects/portfolio/.quality-runner/runs/parallel-20260702T200935Z-portfolio` | exact-project | complete | `019f257b-11a2-7411-8101-c3a992165b3c` | planned; `triage-20260702-portfolio`; no missing capabilities; 17 findings | `368245c` | pushed | Classification `mixed-blocker`. Added Prettier/pnpm gate config, formatter/dead-code/smoke gates, lockfile updates, and truth update. Final QR has zero missing capabilities; `pnpm smoke` and direct `tsc` passed, while `format` and `audit:dead-code` expose broad existing debt. QR still scanned ignored untracked files under `Redesign Basketball Project Dashboard/`. |
| 3 | video-pipeline | `/Users/jakyeamos/projects/video-pipeline` | 20 | 4 | `/Users/jakyeamos/projects/video-pipeline/.quality-runner/runs/parallel-20260702T200935Z-video-pipeline` | parent-project | complete | `019f257b-1afd-7481-bbeb-66bbeb00b6d8` | planned; `triage-20260702-video-pipeline`; no missing capabilities; 12 findings | `392ec7e`, `8a493bb` | pushed | Classification `broad-repo-debt`. Migrated quality gates to pnpm, removed npm lock, added pnpm lock/workspace build approval, and updated truth file. `pnpm install --frozen-lockfile`, `lint`, `test`, and `smoke` passed; `format` and `audit:dead-code` fail on broad existing formatting and unused-symbol debt. |
| 4 | pre-cr-suite-lsp | `/Users/jakyeamos/projects/pre-cr-suite-lsp` | 19 | 1 | `/Users/jakyeamos/projects/pre-cr-suite-lsp/.quality-runner/runs/parallel-20260702T200935Z-pre-cr-suite-lsp` | exact-project | blocked | `019f25c0-d8ae-7761-ae11-f73b50a34e5d` | run planned; verify failed; missing `formatter`, `runtime_smoke` | not created | not pushed | Classification `mixed-blocker`. Traversal healthy, but `verify-gates` executed raw package script bodies instead of pnpm/corepack package-manager context, causing false failures for lint/typecheck/tests; failed gate entries also lacked useful stdout/stderr diagnostics. |
| 4 | Hoopscout | `/Users/jakyeamos/projects/Hoopscout` | 18 | 3 | `/Users/jakyeamos/projects/Hoopscout/.quality-runner/runs/parallel-20260702T200935Z-Hoopscout` | exact-project | blocked | `019f25c0-deb2-7812-b271-7d1decc0cce9` | run planned; verify failed; failed lint/typecheck/build | not created | not pushed | Classification `scanner-product-issue`. QR detected pnpm but executed raw script bodies (`eslint`, `tsc`, `next`) so local bin resolution failed even though `pnpm exec` resolved all three; `quality-runner status` also reported `ready` after latest failed verify run. |
| 4 | career-ops | `/Users/jakyeamos/projects/career-ops` | 17 | 5 | `/Users/jakyeamos/projects/career-ops/.quality-runner/runs/parallel-20260702T200935Z-career-ops` | parent-project | blocked | `019f25c0-e92c-7203-93a8-120be47e2e62` | run planned; verify blocked; gates empty | not created | not pushed | Classification `mixed-blocker`. QR found no executable gates despite existing `.aios-quality-gate.json`; preflight detected npm from `package-lock.json` while handoff recommended pnpm; repo includes Go but capability coverage remained JavaScript-centric; console-output findings were noisy for a CLI-style repo. |
| 4 | Crimclock | `/Users/jakyeamos/projects/Crimclock` | 16 | 1 | `/Users/jakyeamos/projects/Crimclock/.quality-runner/runs/parallel-20260702T200935Z-Crimclock` | exact-project | blocked | `019f25c0-f096-7622-b3d2-8f49bf4f2502` | run planned; verify failed; missing `dead_code`; failed formatter/tests/pre_pr | not created | not pushed | Classification `mixed-blocker`. Real repo/env blockers remain, but QR also discovered `github-actions pull_request quality` and tried to execute it locally; `nested-ternary` heuristic flagged TypeScript nullish coalescing, optional chaining fallbacks, union bars, regex alternation, and template expressions. |
| 4 | Crimclock-pr1-audit | `/Users/jakyeamos/projects/Crimclock-pr1-audit` | 16 | 1 | `/Users/jakyeamos/projects/Crimclock-pr1-audit/.quality-runner/runs/parallel-20260702T200935Z-Crimclock-pr1-audit` | parent-project | blocked | `019f25c0-fc94-70b0-8e64-49261fdcb525` | run planned; verify failed; missing `dead_code`; failed formatter/tests/pre_pr | not created | not pushed | Classification `mixed-blocker`. Same CI-only pseudo-command issue as Crimclock; handoff `planned` is too weak after gate verification fails; run manifests lack explicit completion status/duration fields useful to controllers. |
| 5 | frmwrklabs | `/Users/jakyeamos/projects/frmwrklabs` | 16 | 4 | `/Users/jakyeamos/projects/frmwrklabs/.quality-runner/runs/parallel-20260702T200935Z-frmwrklabs` | exact-project | blocked | `019f25e9-10df-76e2-97a6-6d88a8915353` | findings; `stress-20260703-frmwrklabs-postcommit-verify`; executable gates passed | `b7c8218` | pushed | Classification `broad-repo-debt`. Added canonical pnpm gates, a dependency-free gate helper, image dimensions, blog generator cleanup, and truth update. Final verify passed 9 gates through `pnpm run`; audit remains blocked by broad structural buckets including spacing scale, deep nesting, reveal styles, pass-through wrappers, unsafe HTML warning, console output, reduced motion, and side-stripe border. |
| 5 | BIP-Console | `/Users/jakyeamos/projects/BIP-Console` | 15 | 3 | `/Users/jakyeamos/projects/BIP-Console/.quality-runner/runs/parallel-20260702T200935Z-BIP-Console` | exact-project | blocked | `019f25e9-1a10-7022-8717-443697a923e1` | blocked; `stress-20260703-BIP-Console-final2-verify`; missing capabilities cleared | `cf65a9e1dcfaff1ce59f2a51c6be043ee0603a08` | pushed | Classification `mixed-blocker`. Added format/lint/dead-code/smoke/pre-pr gates, explicit pnpm build policy, compiled-CLI test execution, Vitest timeout, removed one unused helper, and truth/audit updates. Direct `pnpm pre-pr` passes, but QR-spawned `pnpm test` still times out local-server tests; final audit also has 135 raw structural findings. |
| 5 | Book-documents-github | `/Users/jakyeamos/projects/Book-documents-github` | 15 | 5 | `/Users/jakyeamos/projects/Book-documents-github/.quality-runner/runs/parallel-20260702T200935Z-Book-documents-github` | parent-project | blocked | `019f25e9-2131-7c91-9805-f71e5d0a2eba` | blocked; `stress-20260703-Book-documents-github-final-verify`; executable gates passed | `d73fb4eed83bb31f8899d491c9a97b7a836d6027` | pushed | Classification `broad-repo-debt`. Migrated quality commands and workflows from npm to pnpm, added QR-discoverable gates including `pre-cr`, removed npm lock, added pnpm lock, and updated truth/docs. Final verify passed package gates and skipped CI-only `pre_pr`; audit remains blocked by 303 structural findings. Localhost smoke needed unsandboxed QR verification because sandboxed bind failed with `EPERM`. |
| 5 | eslint-plugin-anti-slop | `/Users/jakyeamos/projects/eslint-plugin-anti-slop` | 12 | 4 | `/Users/jakyeamos/projects/eslint-plugin-anti-slop/.quality-runner/runs/parallel-20260702T200935Z-eslint-plugin-anti-slop` | exact-project | blocked | `019f25e9-29d0-7fd3-8cb3-2d80420e9db8` | blocked; `stress-20260703-eslint-plugin-anti-slop-final2-verify`; executable gates passed | `45fab9a`, `b999af8` | pushed | Classification `broad-repo-debt`. Added dependency-free format/typecheck/dead-code gates, build/smoke aliases, canonical QR truth file, PR template whitespace fix, and planning state update. Final verify passed all executable `pnpm run` gates and skipped CI-only/non-command capabilities; audit remains blocked by 135 structural findings. Regex `(?:...)` still produces nested-ternary false positives. |
| 5 | R-Project | `/Users/jakyeamos/projects/R-Project` | 12 | 5 | `/Users/jakyeamos/projects/R-Project/.quality-runner/runs/parallel-20260702T200935Z-R-Project` | parent-project | complete | `019f25e9-312e-7210-ad57-0cedf96da403` | clean/passed; `stress-20260703-R-Project-final-verify` | `5584cba` | pushed | Classification `clean-after-config`. Added `.quality-runner.toml` for the existing R test/pre-CR gate and excluded vendored `.Rlibs` from scanning, plus truth update. Final `run` was clean, final `verify-gates` passed, both executable R gates reported `57 / 57 tests passed`, and `quality-runner status` reported ready. Product lesson: requiring `truth_file` in executable verification caused a blocked verify until config limited required capabilities to executable gates. |
| 6 | Terrace | `/Users/jakyeamos/projects/Terrace` | 12 | 2 | `/Users/jakyeamos/projects/Terrace/.quality-runner/runs/parallel-20260702T200935Z-Terrace` | exact-project | pending |  |  |  |  |  |
| 6 | tmcp | `/Users/jakyeamos/projects/tmcp` | 11 | 5 | `/Users/jakyeamos/projects/tmcp/.quality-runner/runs/parallel-20260702T200935Z-tmcp` | exact-project | pending |  |  |  |  |  |
| 6 | claude-config | `/Users/jakyeamos/projects/claude-config` | 10 | 5 | `/Users/jakyeamos/projects/claude-config/.quality-runner/runs/parallel-20260702T200935Z-claude-config` | parent-project | pending |  |  |  |  |  |
| 6 | agent-router | `/Users/jakyeamos/projects/agent-router` | 9 | 5 | `/Users/jakyeamos/projects/agent-router/.quality-runner/runs/parallel-20260702T200935Z-agent-router` | exact-project | pending |  |  |  |  |  |
| 6 | claude-improvement-lab | `/Users/jakyeamos/projects/claude-improvement-lab` | 9 | 5 | `/Users/jakyeamos/projects/claude-improvement-lab/.quality-runner/runs/parallel-20260702T200935Z-claude-improvement-lab` | parent-project | pending |  |  |  |  |  |
| 7 | context-compiler-contract | `/Users/jakyeamos/projects/context-compiler-contract` | 9 | 4 | `/Users/jakyeamos/projects/context-compiler-contract/.quality-runner/runs/parallel-20260702T200935Z-context-compiler-contract` | parent-project | pending |  |  |  |  |  |
| 7 | dotfiles | `/Users/jakyeamos/projects/dotfiles` | 9 | 5 | `/Users/jakyeamos/projects/dotfiles/.quality-runner/runs/parallel-20260702T200935Z-dotfiles` | exact-project | pending |  |  |  |  |  |
| 7 | jakyeamos-profile | `/Users/jakyeamos/projects/jakyeamos-profile` | 9 | 5 | `/Users/jakyeamos/projects/jakyeamos-profile/.quality-runner/runs/parallel-20260702T200935Z-jakyeamos-profile` | parent-project | pending |  |  |  |  |  |
| 7 | New project | `/Users/jakyeamos/projects/New project` | 9 | 5 | `/Users/jakyeamos/projects/New project/.quality-runner/runs/parallel-20260702T200935Z-New-project` | parent-project | pending |  |  |  |  |  |
| 7 | untitled1 | `/Users/jakyeamos/projects/untitled1` | 9 | 5 | `/Users/jakyeamos/projects/untitled1/.quality-runner/runs/parallel-20260702T200935Z-untitled1` | parent-project | pending |  |  |  |  |  |
| 8 | LaxDS | `/Users/jakyeamos/projects/LaxDS` | 8 | 3 | `/Users/jakyeamos/projects/LaxDS/.quality-runner/runs/parallel-20260702T200935Z-LaxDS` | parent-project | pending |  |  |  |  |  |
| 8 | manga-sync | `/Users/jakyeamos/projects/manga-sync` | 8 | 5 | `/Users/jakyeamos/projects/manga-sync/.quality-runner/runs/parallel-20260702T200935Z-manga-sync` | parent-project | pending |  |  |  |  |  |
| 8 | tm | `/Users/jakyeamos/projects/tm` | 7 | 1 | `/Users/jakyeamos/projects/tm/.quality-runner/runs/parallel-20260702T200935Z-tm` | parent-project | pending |  |  |  |  |  |
| 8 | greenlight | `/Users/jakyeamos/projects/greenlight` | 6 | 3 | `/Users/jakyeamos/projects/greenlight/.quality-runner/runs/parallel-20260702T200935Z-greenlight` | parent-project | pending |  |  |  |  |  |
| 8 | repo-quality-certifier | `/Users/jakyeamos/projects/repo-quality-certifier` | 5 | 2 | `/Users/jakyeamos/projects/repo-quality-certifier/.quality-runner/runs/parallel-20260702T200935Z-repo-quality-certifier` | parent-project | pending |  |  |  |  |  |
| 9 | research-domain-writing | `/Users/jakyeamos/projects/research-domain-writing` | 5 | 2 | `/Users/jakyeamos/projects/research-domain-writing/.quality-runner/runs/parallel-20260702T200935Z-research-domain-writing` | parent-project | pending |  |  |  |  |  |
| 9 | agent-eval-contract | `/Users/jakyeamos/projects/agent-eval-contract` | 4 | 2 | `/Users/jakyeamos/projects/agent-eval-contract/.quality-runner/runs/parallel-20260702T200935Z-agent-eval-contract` | parent-project | pending |  |  |  |  |  |
| 9 | quality-evidence-contract | `/Users/jakyeamos/projects/quality-evidence-contract` | 4 | 2 | `/Users/jakyeamos/projects/quality-evidence-contract/.quality-runner/runs/parallel-20260702T200935Z-quality-evidence-contract` | parent-project | pending |  |  |  |  |  |
| 9 | quality-runner | `/Users/jakyeamos/projects/quality-runner` | 2 | 0 | `/Users/jakyeamos/projects/quality-runner/.quality-runner/runs/parallel-20260702T200935Z-quality-runner` | exact-project | pending |  |  |  |  |  |
