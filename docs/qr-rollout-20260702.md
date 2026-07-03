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
| 1 | `tenure` | `/Users/jakyeamos/projects/tenure` | `wave1-restart-20260702-tenure-targeted` | running | `019f2646-6119-7de3-b58e-810b1c5f8d25` |  |  | Parent-project thread scoped to exact repo path. |
| 1 | `BidCamp` | `/Users/jakyeamos/projects/BidCamp` | `wave1-restart-20260702-BidCamp-2` | running | `019f2646-69d9-7bb3-8dce-28e4003dbfcf` |  |  | Exact-project thread. |
| 1 | `AIOS` | `/Users/jakyeamos/projects/AIOS` | `wave1-restart-20260702-AIOS` | running | `019f2646-7846-7150-986c-145d7898d1d2` |  |  | Parent-project thread scoped to exact repo path. |
| 1 | `amos-saas` | `/Users/jakyeamos/projects/amos-saas` | `wave1-restart-20260702-amos-saas` | running | `019f2646-81b3-7091-b4d7-5d7f6c6283fd` |  |  | Parent-project thread scoped to exact repo path. |
| 1 | `Dsci-proj` | `/Users/jakyeamos/projects/Dsci-proj` | `triage-20260702-Dsci-proj` | running | `019f2646-8a93-72d3-b68c-fe79feb6eb80` |  |  | Parent-project thread scoped to exact repo path. |

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
