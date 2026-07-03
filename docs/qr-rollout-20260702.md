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

Wave 1 should not advance until every worker returns `complete` or `blocked`.
Early worker reports used `ready-for-review` after clearing missing repo-owned
gates but before clearing runner-provided findings. The controller tightened the
terminal vocabulary so partial progress remains `running` and gets returned to
the worker.

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

## Rollout Ledger

| Wave | Repo | Repo path | Total | Blockers | Baseline artifacts | Codex project status | Thread status | Thread id | Final QR status | Commit | Push | Notes |
|---:|---|---|---:|---:|---|---|---|---|---|---|---|---|
| 1 | tenure | `/Users/jakyeamos/projects/tenure` | 45 | 4 | `/Users/jakyeamos/projects/tenure/.quality-runner/runs/parallel-20260702T200935Z-tenure` | parent-project | running | `019f24fa-9946-7983-95be-33d1326f49ac` | planned; post-targeted fixed-runner QR run, awaiting terminal report | `de0ece0` | pushed | Worker removed four high-signal findings and updated truth file, then stalled before commit/push/report; controller nudge sent. Wave 1 cannot close until this thread reports `complete` or `blocked`. |
| 1 | BidCamp | `/Users/jakyeamos/projects/BidCamp` | 39 | 2 | `/Users/jakyeamos/projects/BidCamp/.quality-runner/runs/parallel-20260702T200935Z-BidCamp` | exact-project | blocked | `019f24fa-d0d8-7821-a901-b186a39ecb15` | planned; `wave1-restart-20260702-BidCamp-2` | `60ffe151` | pushed | Fixed-runner restart added scoped QR config and image dimensions; `pnpm pre-cr` and dummy-env build passed. Blocked by 3,539 structural instances, 3,039 in `src`, requiring broad source refactor rather than scoped QR cleanup. |
| 1 | Vaults | `/Users/jakyeamos/projects/Vaults` | 39 | 5 | `/Users/jakyeamos/projects/Vaults/.quality-runner/runs/parallel-20260702T200935Z-Vaults` | parent-project | complete | `019f24fa-fe62-7f60-b832-798ee07f82bd` | clean | `2f19af9` | pushed | Restart verification clean with fixed runner: `wave1-restart-20260702-Vaults`; no new commit. |
| 1 | AIOS | `/Users/jakyeamos/projects/AIOS` | 34 | 1 | `/Users/jakyeamos/projects/AIOS/.quality-runner/runs/parallel-20260702T200935Z-AIOS` | parent-project | blocked | `019f24fb-3107-79a0-9af9-2a6de33f22ac` | planned; findings; no missing capabilities | `4031d38` | pushed | Restart run `wave1-restart-20260702-AIOS` with fixed QR runner dropped findings from 24,572 to 666; remaining blocker is broad repo-owned source debt. |
| 1 | amos-saas | `/Users/jakyeamos/projects/amos-saas` | 34 | 2 | `/Users/jakyeamos/projects/amos-saas/.quality-runner/runs/parallel-20260702T200935Z-amos-saas` | parent-project | blocked | `019f24fb-5f5d-7f91-bfb8-43e9f3744be4` | findings; `wave1-restart-20260702-amos-saas`; no missing capabilities | `7ad2690` | pushed | Restart produced no new commit; branch already pushed. Blocked by 27 grouped / 1,160 raw structural findings across 241 files, missing local env secrets, and dependency audit network policy. |
| 2 | Dsci-proj | `/Users/jakyeamos/projects/Dsci-proj` | 30 | 2 | `/Users/jakyeamos/projects/Dsci-proj/.quality-runner/runs/parallel-20260702T200935Z-Dsci-proj` | parent-project | pending |  |  |  |  |  |
| 2 | Bballedu | `/Users/jakyeamos/projects/Bballedu` | 28 | 1 | `/Users/jakyeamos/projects/Bballedu/.quality-runner/runs/parallel-20260702T200935Z-Bballedu` | parent-project | pending |  |  |  |  |  |
| 2 | BBDSE | `/Users/jakyeamos/projects/BBDSE` | 27 | 1 | `/Users/jakyeamos/projects/BBDSE/.quality-runner/runs/parallel-20260702T200935Z-BBDSE` | exact-project | pending |  |  |  |  |  |
| 2 | EliHealth | `/Users/jakyeamos/projects/EliHealth` | 27 | 2 | `/Users/jakyeamos/projects/EliHealth/.quality-runner/runs/parallel-20260702T200935Z-EliHealth` | exact-project | pending |  |  |  |  |  |
| 2 | Fantasy | `/Users/jakyeamos/projects/Fantasy` | 27 | 4 | `/Users/jakyeamos/projects/Fantasy/.quality-runner/runs/parallel-20260702T200935Z-Fantasy` | exact-project | pending |  |  |  |  |  |
| 3 | Book | `/Users/jakyeamos/projects/Book` | 22 | 4 | `/Users/jakyeamos/projects/Book/.quality-runner/runs/parallel-20260702T200935Z-Book` | exact-project | pending |  |  |  |  |  |
| 3 | dispatches-from-cyberspace | `/Users/jakyeamos/projects/dispatches-from-cyberspace` | 22 | 2 | `/Users/jakyeamos/projects/dispatches-from-cyberspace/.quality-runner/runs/parallel-20260702T200935Z-dispatches-from-cyberspace` | parent-project | pending |  |  |  |  |  |
| 3 | remodelvision | `/Users/jakyeamos/projects/remodelvision` | 22 | 2 | `/Users/jakyeamos/projects/remodelvision/.quality-runner/runs/parallel-20260702T200935Z-remodelvision` | exact-project | pending |  |  |  |  |  |
| 3 | portfolio | `/Users/jakyeamos/projects/portfolio` | 20 | 2 | `/Users/jakyeamos/projects/portfolio/.quality-runner/runs/parallel-20260702T200935Z-portfolio` | exact-project | pending |  |  |  |  |  |
| 3 | video-pipeline | `/Users/jakyeamos/projects/video-pipeline` | 20 | 4 | `/Users/jakyeamos/projects/video-pipeline/.quality-runner/runs/parallel-20260702T200935Z-video-pipeline` | parent-project | pending |  |  |  |  |  |
| 4 | pre-cr-suite-lsp | `/Users/jakyeamos/projects/pre-cr-suite-lsp` | 19 | 1 | `/Users/jakyeamos/projects/pre-cr-suite-lsp/.quality-runner/runs/parallel-20260702T200935Z-pre-cr-suite-lsp` | exact-project | pending |  |  |  |  |  |
| 4 | Hoopscout | `/Users/jakyeamos/projects/Hoopscout` | 18 | 3 | `/Users/jakyeamos/projects/Hoopscout/.quality-runner/runs/parallel-20260702T200935Z-Hoopscout` | exact-project | pending |  |  |  |  |  |
| 4 | career-ops | `/Users/jakyeamos/projects/career-ops` | 17 | 5 | `/Users/jakyeamos/projects/career-ops/.quality-runner/runs/parallel-20260702T200935Z-career-ops` | parent-project | pending |  |  |  |  |  |
| 4 | Crimclock | `/Users/jakyeamos/projects/Crimclock` | 16 | 1 | `/Users/jakyeamos/projects/Crimclock/.quality-runner/runs/parallel-20260702T200935Z-Crimclock` | exact-project | pending |  |  |  |  |  |
| 4 | Crimclock-pr1-audit | `/Users/jakyeamos/projects/Crimclock-pr1-audit` | 16 | 1 | `/Users/jakyeamos/projects/Crimclock-pr1-audit/.quality-runner/runs/parallel-20260702T200935Z-Crimclock-pr1-audit` | parent-project | pending |  |  |  |  |  |
| 5 | frmwrklabs | `/Users/jakyeamos/projects/frmwrklabs` | 16 | 4 | `/Users/jakyeamos/projects/frmwrklabs/.quality-runner/runs/parallel-20260702T200935Z-frmwrklabs` | exact-project | pending |  |  |  |  |  |
| 5 | BIP-Console | `/Users/jakyeamos/projects/BIP-Console` | 15 | 3 | `/Users/jakyeamos/projects/BIP-Console/.quality-runner/runs/parallel-20260702T200935Z-BIP-Console` | exact-project | pending |  |  |  |  |  |
| 5 | Book-documents-github | `/Users/jakyeamos/projects/Book-documents-github` | 15 | 5 | `/Users/jakyeamos/projects/Book-documents-github/.quality-runner/runs/parallel-20260702T200935Z-Book-documents-github` | parent-project | pending |  |  |  |  |  |
| 5 | eslint-plugin-anti-slop | `/Users/jakyeamos/projects/eslint-plugin-anti-slop` | 12 | 4 | `/Users/jakyeamos/projects/eslint-plugin-anti-slop/.quality-runner/runs/parallel-20260702T200935Z-eslint-plugin-anti-slop` | exact-project | pending |  |  |  |  |  |
| 5 | R-Project | `/Users/jakyeamos/projects/R-Project` | 12 | 5 | `/Users/jakyeamos/projects/R-Project/.quality-runner/runs/parallel-20260702T200935Z-R-Project` | parent-project | pending |  |  |  |  |  |
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
