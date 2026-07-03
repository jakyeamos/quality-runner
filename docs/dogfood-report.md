# Dogfood Report

Date: 2026-06-28

Quality Runner was run against the committed fixture corpus under `fixtures/corpus`.

| Fixture | Expected status | Purpose |
| --- | --- | --- |
| `complete-js` | `clean` | Full JavaScript quality surface with pnpm, Pre-CR, smoke, pre-pr, and truth file. |
| `mature-mixed` | `planned` | Mixed Python/JS repo with Make, Docker, Terraform, migrations, OpenAPI, Protobuf, generated code, monorepo metadata, explicit local policy, and one deliberate missing dead-code gate. |
| `partial-js` | `planned` | Minimal JavaScript repo with only lint configured. |
| `python-empty` | `planned` | Python repo with no runnable quality commands configured. |

The corpus is intentionally small. It protects the baseline product contract:
clean repos stay clean, incomplete repos produce remediation slices, and all runs
write the public artifact set including `run-manifest.json`.

The `mature-mixed` fixture is the senior-review proxy. It proves Quality Runner
can distinguish broad mature-codebase evidence from actual missing quality
capabilities: Make targets, Docker runtime files, Terraform configuration, DB
migrations, service contracts, generated code, and monorepo task runners are
recognized as repo surfaces, while the intentionally absent dead-code gate stays
as the planned remediation item.

## External Dogfood Run

Date: 2026-07-01

Quality Runner was run against this repo plus four shallow-cloned public repos.
The run table records the public repo name, commit, status, useful signal, and
known scanner noise from that snapshot.

| Repo | Category | Commit | Run status | Useful signal | Noise or gap |
| --- | --- | --- | --- | --- | --- |
| `quality-runner` | Self-audit | `217c2c4` | `clean` | Detected the Python quality ladder, CI-backed gates, Pre-CR config, and no missing required capabilities. | Surface discovery also sees mature fixture files under `fixtures/corpus`; future scan policy should support fixture/test exclusions. |
| `fastapi/full-stack-fastapi-template` | Python backend/full-stack | `3685fb6` | `planned` | Detected a mixed Python/JS repo, Docker Compose, frontend lint/test scripts, backend test workflow, and pull-request CI evidence. | Root-only Python discovery missed `backend/pyproject.toml` tool evidence; personal pnpm policy flags `bun` even though this repo intentionally uses it. |
| `nextjs/saas-starter` | JS/TS app | `6e33e58` | `planned` | Correctly found `pnpm` and the build script. The missing lint/typecheck/test/smoke findings are useful because the root `package.json` has only dev/build/start/db scripts. | No major scanner noise observed; a senior reviewer would still inspect app-specific CI if added later. |
| `vercel/turborepo` | Mixed monorepo/task-runner repo | `b426736` | `planned` | Detected `pnpm`, `turbo.json`, `pnpm-workspace.yaml`, protobuf contracts, format/lint/test/build scripts, and pull-request CI evidence. | Missed repo-specific quality semantics such as `check`, `build:ts`, Rust/Cargo gates, and release workflows; this needs workspace-aware command classification. |
| `emilybache/GildedRose-Refactoring-Kata` | Intentionally messy/legacy sample | `3e0085b` | `planned` | Produced a high-signal incomplete-quality posture: no root package manager, quality ladder, smoke, dead-code, or Pre-CR evidence. | Root-only scanning misses many nested language examples; this is acceptable as a first finding but not enough for mature polyglot audits. |

Run artifacts:

- `quality-runner`: `.quality-runner/runs/dogfood-quality-runner-2026-07-01/`
- `python-backend-fastapi-template`: `.quality-runner/runs/dogfood-python-backend-2026-07-01/`
- `js-ts-nextjs-saas-starter`: `.quality-runner/runs/dogfood-js-ts-app-2026-07-01/`
- `mixed-monorepo-turborepo`: `.quality-runner/runs/dogfood-mixed-monorepo-2026-07-01/`
- `intentionally-messy-gildedrose`: `.quality-runner/runs/dogfood-messy-gildedrose-2026-07-01/`

### Senior Review Takeaway

The external run validates the core product shape: Quality Runner is useful as
an evidence normalizer and missing-gate planner, especially for repos with clear
root-level package scripts, CI workflows, Docker/Compose files, and monorepo
markers.

The next improvement should be evidence-driven, not another broad detector pass:

1. Add recursive workspace discovery for nested `pyproject.toml`,
   `package.json`, Cargo, Go, and language-specific project roots.
2. Make package-manager policy configurable per repo so intentional Bun/Yarn/npm
   projects are not flagged by a personal pnpm default.
3. Expand command classification to understand repo-specific quality aliases
   such as `check`, `build:ts`, `pre-commit`, `prek`, `ultracite`, Cargo tests,
   and backend scripts invoked from CI.
4. Add scan exclusions for fixtures, generated corpora, vendored examples, and
   docs so self-audits do not over-report intentionally embedded sample repos.

This is the hiring-manager proof point: the tool now has real-world evidence,
known limitations, and a concrete next roadmap derived from observed behavior
rather than speculative feature ideas.

## Evidence-Driven Fix Rerun

Date: 2026-07-01

After the first external run, Quality Runner added:

- recursive workspace discovery for nested `package.json`, `pyproject.toml`,
  `Cargo.toml`, and `go.mod`
- quality alias classification for commands such as `check`, `build:ts`,
  `mypy`, `ty`, and `prek`
- a bounded workspace inventory with a 200-workspace cap and warning
- configurable `allowed_package_managers` in `.quality-runner.toml`

| Repo | Before | After | Change |
| --- | --- | --- | --- |
| `quality-runner` | `clean`, 0 workspaces | `clean`, 5 fixture workspaces | Still clean; fixture workspaces are now visible evidence. |
| `fastapi/full-stack-fastapi-template` | 6 findings | 2 findings | Nested `backend/pyproject.toml`, `frontend/package.json`, and `prek` evidence removed false missing formatter/typecheck/build/Pre-CR findings. Remaining findings: missing dead-code and package-manager policy mismatch. |
| `nextjs/saas-starter` | 8 findings | 8 findings | No change; this remains useful evidence that the app has build/db scripts but no explicit lint/typecheck/test/smoke/CI gates in the cloned root. |
| `vercel/turborepo` | 4 findings, 0 workspaces | 4 findings, 200 capped workspaces | Recursive scan detects JS/Rust workspaces and removes the false missing typecheck finding. A workspace-limit warning is now emitted instead of writing an unreadable 1,095-workspace artifact. |
| `emilybache/GildedRose-Refactoring-Kata` | 8 findings, no languages | 7 findings, 8 workspaces | Nested JS/Go/Rust workspaces and JS test scripts are now detected, removing the false missing tests finding. |

Rerun artifacts:

- `quality-runner`: `.quality-runner/runs/dogfood-quality-runner-fixed-2026-07-01/`
- `python-backend-fastapi-template`: `.quality-runner/runs/dogfood-python-backend-fixed-2026-07-01/`
- `js-ts-nextjs-saas-starter`: `.quality-runner/runs/dogfood-js-ts-app-fixed-2026-07-01/`
- `mixed-monorepo-turborepo`: `.quality-runner/runs/dogfood-mixed-monorepo-fixed-2026-07-01/`
- `intentionally-messy-gildedrose`: `.quality-runner/runs/dogfood-messy-gildedrose-fixed-2026-07-01/`

The senior-review conclusion improved: Quality Runner now converts real
dogfood evidence into targeted product changes and can demonstrate measurable
noise reduction without weakening the audit boundary.

## Scan Exclusion Fix Rerun

Date: 2026-07-02

The next dogfood pass targeted the remaining Quality Runner self-audit noise:
embedded fixture workspaces under `fixtures/corpus` were useful for tests but
not product workspaces.

Quality Runner now applies default scan exclusions for `docs`, `fixtures`,
`corpus`, `generated-corpus`, `generated-corpora`, `vendor`, `vendors`,
`vendored`, and `third_party`, with repo-specific additions available through
`.quality-runner.toml` as `scan_exclusions`.

Evidence:

- `quality-runner inspect . --run-id dogfood-scan-exclusions-2026-07-02 --json`
- `repo-scan.json` reports `workspaces: []` for Quality Runner itself.
- `repo-scan.json` records the active `scan_exclusions` list for auditability.

Result: Quality Runner no longer reports its fixture corpus as nested
workspaces by default, while standalone fixture-corpus tests still run against
those repos explicitly.

## Pre-Release Refresh Handoff Dogfood

Date: 2026-07-03

This pass targeted the release-critical user workflow: run QR with
`refresh --handoff-output`, then work from the generated remediation handoff
without opening raw JSON first.

| Repo shape | Command | Result | Handoff | Signal |
| --- | --- | --- | --- | --- |
| Small generated repo | `quality-runner release-smoke --work-dir /private/tmp/qr-release-smoke-self --json` | passed | `/private/tmp/qr-release-smoke-self/release-smoke-handoff.md` | Help, doctor, refresh handoff export, export-handoff, and controller report schema compatibility all passed. |
| JS app (`BIP-Console`) | `quality-runner refresh /Users/jakyeamos/projects/BIP-Console --run-id-prefix prerelease-dogfood-bip-20260703 --handoff-output /private/tmp/qr-prerelease-bip-handoff.md --timeout-seconds 60 --verify-timeout-seconds 180 --total-timeout-seconds 300 --total-timeout-reason "pre-release dogfood JS app evidence budget" --json` | blocked | `/private/tmp/qr-prerelease-bip-handoff.md` | All executable JS gates passed; QR correctly blocked on read-only formatter policy and 10 structural findings. |
| Large messy repo (`BBDSE`) | `quality-runner refresh /Users/jakyeamos/projects/BBDSE --run-id-prefix prerelease-dogfood-bbdse-20260703 --handoff-output /private/tmp/qr-prerelease-bbdse-handoff.md --timeout-seconds 30 --verify-timeout-seconds 90 --total-timeout-seconds 120 --total-timeout-reason "pre-release dogfood large repo traversal budget" --json` | blocked | `/private/tmp/qr-prerelease-bbdse-handoff.md` | Timeout evidence now reports total elapsed around 120s, includes phase elapsed, top-level traversal counts, and confirms `.claude/worktrees` is skipped. |

Release takeaway: the public workflow is shippable for small repos and normal JS
apps. Large-repo timeout evidence is now trustworthy and readable, but BBDSE
still needs repo-specific scan policy for large source/data surfaces before it
can complete under a bounded release-smoke budget.
