# Agent Usage

Quality Runner gives agents evidence, an outcome, and a handoff. QR can also
maintain advisory phase and delivery plans; the external agent or human still
owns source changes, commits, pushes, and execution decisions. Use this page
for the operating protocol and the [CLI Reference](cli.md) for exhaustive
options and artifact details.

## Invocation

The examples below use `quality-runner` for readability. Consumer repositories
should use the source-first contract in [Consumer Tooling](consumer-tooling.md):
`uvx --refresh --from git+https://github.com/jakyeamos/quality-runner.git
quality-runner ...` for latest QR, or `uv run --project /path/to/quality-runner
quality-runner ...` for a specific checkout.

## Choose the QR journey

Use the canonical `qr` command for new work. `quality-runner` is a compatible
alias. Confirm the installation, then choose the smallest journey that matches
the task:

```bash
qr doctor --json
qr audit /path/to/repo --run-id qr-<date-or-task> --json
qr review /path/to/repo --mode blind --run-id review-<date-or-task> --json
qr verify /path/to/repo --run-id qr-<date-or-task>-verify --json
qr runs /path/to/repo --json
```

- `doctor` checks local installation readiness.
- If the installed command is stale relative to a local checkout, use
  `qr self-update --source /path/to/quality-runner --json` and rerun `doctor`.
- `audit` inspects the repository and prepares audit, remediation, and handoff
  evidence without editing source.
- `review` is Fresh Review: it prepares an immutable packet, then validates a
  locally supplied response bound to that packet. A packet-ready or
  `awaiting-evidence` result is not a clean review. Use `--mode task` or
  `--mode combined` only when the task input is available.
- `verify` records gate evidence. It stays evidence-only unless the caller
  explicitly authorizes `--execute-gates --worktree-mode disposable`.
- `runs` reads bounded run history and does not create a new summary artifact.

For a review response, reuse the run id and the response path printed by the
preparation result; never hand-edit packet identity fields:

```bash
qr review /path/to/repo \
  --run-id review-<date-or-task> \
  --adapter-output .quality-runner/runs/review-<date-or-task>/review-adapter-response.json \
  --json
```

For `audit`, `review`, `verify`, and `runs`, parse the v2 outcome
(`quality-runner-outcome-v0.2`) rather than treating exit code `0` as semantic
success. Read its `state`, `assessment`, evidence strength, writes, safety
mode, and `next_action`; blocked, limited, and awaiting-evidence states are
truthful outcomes that require routing.

Use the established `refresh` workflow below when a controller needs one
combined inspect/run/verify/handoff cycle, adaptive refresh controls, or the
task-scoped implement-review loop.

## Choose scan scope explicitly

QR excludes fixture, documentation, vendored, generated, and tool-output trees
by default. An agent must make the scan boundary explicit when the task names a
repository-owned file under one of those defaults:

- use `--include-path <path>` for a bounded scan that re-includes the requested
  path;
- use `--include-ignored-path <path>` to re-include that path while preserving
  the rest of the repository scan;
- use `--scan-exclusion <dir>` only for a run-only global overlay, knowing that
  it changes security coverage;
- use `--scan-exclusion-module code_quality=<dir>` or the other supported module
  names when only one QR-owned scanner should omit a directory and security
  coverage must remain.

Review `scan_inclusions` in the generated scan artifacts to prove what was
included. Protected runtime and artifact paths such as `.git`,
`.quality-runner`, `.venv`, `node_modules`, `build`, and `dist` remain
fail-closed. For a persistent exclusion, use `exclusions suggest`, review the
packet, run `exclusions validate`, and apply only a validated report with the
explicit `exclusions apply --apply` consent.

## Established refresh workflow

Run QR before editing:

```bash
quality-runner refresh /path/to/repo \
  --run-id-prefix qr-<date-or-task> \
  --handoff-output /path/to/repo/.quality-runner/exports/qr-handoff.md \
  --json
```

This default refresh records gate evidence; it is not executable-gate proof.
Only use `--execute-gates --worktree-mode disposable` after explicit user
authorization, and treat it as arbitrary local-code execution in a disposable
checkout rather than a sandbox. `--allow-dirty-worktree-verify` permits
verification of `HEAD` while retaining local edits; it does not verify those
edits. For iterative planning, use `--analysis-mode balanced` with
`--cache-mode external`; use `--analysis-mode full` at phase, audit, or release
boundaries. `--cache-mode disabled` is diagnostic. Read cache and analysis
provenance in the artifacts so reused evidence is not mistaken for a fresh
full scan.

Then read:

- `/path/to/repo/.quality-runner/exports/qr-handoff.md`
- `.quality-runner/runs/<run-id>/slice-specs/<next-slice-id>.md` for the
  cold-executor plan on the queued slice (scope, STOP conditions, drift check,
  evidence excerpts)
- `.quality-runner/runs/<run-id>/quality-audit.json`
- `.quality-runner/runs/<run-id>/remediation-plan.json`
- `.quality-runner/runs/<run-id>/remediation-context.json` before editing; this
  is the bounded-slice context and evidence contract for the worker
- `.quality-runner/runs/<run-id>/gate-verification.json`, when present
- `.quality-runner/runs/<run-id>/code-quality-scan.json`, when structural
  findings drive the work
- intent docs listed in the handoff (`PRODUCT.md`, `DESIGN.md`, ADRs, etc.)

Do not edit source before reading the handoff and the relevant artifacts. A
fresh remediation context starts as `needs-understanding`; complete the
required agent evidence for the selected slice and validate it before editing:

```bash
quality-runner validate-remediation-context \
  .quality-runner/runs/<run-id>/remediation-context.json \
  --remediation-plan .quality-runner/runs/<run-id>/remediation-plan.json \
  --json
```

When a repository contains a large generated, cache, or external directory,
review it before adding a persistent exclusion:

```bash
quality-runner exclusions suggest /path/to/repo --json
quality-runner exclusions validate /path/to/repo \
  --packet .quality-runner/runs/<run-id>/scan-exclusion-preflight-packet.json \
  --report /path/to/review.json --json
```

Use a module-scoped decision when only code-quality or structural scanning
should omit the directory. That preserves QR security coverage. Apply a
validated report only with explicit `exclusions apply --apply`; otherwise use
`--scan-exclusion` or `--scan-exclusion-module` for a run-only overlay.

For a single slice, prefer the matching `slice-specs/*.md` file as the
execution contract. Use `remediation-plan.json` for ordering across slices and
`agent-handoff.md` for controller routing.

## QR Slice Spec Contract

When `slice-specs/<slice-id>.md` exists for the queued slice, treat it as the
primary execution spec. It mirrors improve-style cold-executor plans and should
already contain:

- why the slice matters
- current-state evidence excerpts
- in-scope and out-of-scope boundaries
- ordered steps with per-step verification
- done criteria
- STOP conditions (stop and report instead of editing when triggered)
- `planned_at` git state and a drift-check command when the repo is a git
  checkout

Before editing in-scope files, run the slice drift check when `planned_at` is
present. If the excerpt no longer matches the code, stop and refresh QR or
record an accepted disposition rather than guessing.

Validate artifacts before dispatch or after regeneration:

```bash
quality-runner validate-handoff .quality-runner/runs/<run-id>/agent-handoff.json --json
quality-runner validate-remediation-context .quality-runner/runs/<run-id>/remediation-context.json \
  --remediation-plan .quality-runner/runs/<run-id>/remediation-plan.json --json
quality-runner validate-slice-spec .quality-runner/runs/<run-id>/slice-specs/<slice-id>.md --json
```

After a worker finishes, controllers can audit the result read-only:

```bash
quality-runner review-worker /path/to/repo \
  --baseline-run-id <before> \
  --final-run-id <after> \
  --worker-report worker-report.json \
  --json
```

## Route follow-up work through the matching surface

Use the artifact already produced by QR as the source of truth, then choose the
next controller or planning surface:

- For one bounded remediation slice, start with the matching
  `slice-specs/<slice-id>.md`, run its drift check, and validate
  `remediation-context.json` before editing. A rejected context or stale slice
  is a stop condition, not permission to guess.
- For a controller decision on an existing run, use `gate`, `gate-status`, and
  `gate-respond`. These append controller history and dispositions; they do not
  edit source or rerun the scan.
- For a worker completion handoff, run `validate-report` and, when normalizing
  a report, `controller-report lint --strict`; use `review-worker` to compare
  baseline and final QR evidence.
- For an implement-review loop, pass the task through `--intent` or
  `--intent-file` with a stable `--review-cycle-id` and 1-based
  `--review-iteration`. Read `review-delta.json` and `.md`, apply only the
  task-scoped fixes, and stop when the delta recommends `stop`. Unrelated
  findings remain `out_of_scope`.
- If artifacts already exist, use `export-handoff` or `export-slice-specs` to
  regenerate the controller handoff or cold-executor specs without rescanning.
- For multi-repository work, use `rollout` so each repository gets isolated
  run ids and controller artifacts. Rollout is evidence-only by default; use
  the same explicit disposable execution pair for gate execution.
- For QR-owned planning, use `plan auto` and the `phase` commands. For a
  structured execution contract, use `plan contract prepare`,
  `plan contract refresh`, `plan preflight`, and `plan reconcile`. Balanced
  analysis with an external cache is
  appropriate for iterative planning; use full analysis at phase, release, or
  audit boundaries, and use disabled cache only for diagnostics.
- For repository skill evidence, use the skill review/validation surfaces and
  attach the validated report with `--skill-review-report`; see
  [Quality Skills](quality-skills.md).
- Before packaging or publishing, run `release-smoke`. MCP integrations should
  prefer the four additive outcome tools and treat `tools/list` as the current
  registry; v1 tools remain compatibility surfaces.

The exact command forms and artifact schemas are maintained in the
[CLI Reference](cli.md), [Artifact Contract](artifacts.md),
[Planning and Delivery Contracts](planning-contracts.md), and
[MCP Integration](mcp.md). Do not infer a new command or artifact name from an
older handoff.

## Native QR Phase Workflow

Initialize the QR-owned namespace after the first useful run:

```bash
quality-runner plan auto /path/to/repo --run-id qr-baseline-run --json
quality-runner phase next /path/to/repo --phase 1 --json
```

`plan auto` creates one native phase per domain candidate in security-first
order and links each phase to its forensic leaf slices. It is idempotent. Older
remediation plans without domain candidates continue to work through leaf
slices. Each plan records source references, scope, tasks, stop conditions,
verification gates, dependencies, and a deterministic wave; QR dispatches the
next ready plan but does not execute it.

After an external batch, record and verify it:

```bash
quality-runner phase record-batch /path/to/repo \
  --phase 1 --plan 1 --result-file batch-result.json --json
quality-runner phase update /path/to/repo \
  --phase 1 --baseline-run-id qr-before --run-id qr-after --json
quality-runner phase verify /path/to/repo --phase 1 --run-id qr-after --json
```

Native planning files live only under `.planning/quality-runner/`. QR does not
modify root GSD files, execute source changes, commit, or push. GSD remains a
valid optional external planning consumer when a repository needs it.

## Required Agent Protocol

Before changing code, write or update planning artifacts in the target repo.
Use the repo's existing planning location when one exists. Otherwise use:

```text
.planning/
  STATE.md
  phases/
    <phase-number>-<slug>/
      PLAN.md
      RESOLUTION-LEDGER.tsv
      <batch-number>-SUMMARY.md
```

Do not treat this as QR-owned output. These files are agent planning artifacts.
QR may reference them later, but QR does not execute them.

## GSD-Style Phase Plan Template

Each phase `PLAN.md` should use this shape:

```md
# Phase <number>: <name>

## Goal

One or two sentences describing the bounded outcome.

## QR Evidence

- QR run id:
- Handoff:
- Primary status/classification:
- Blocker classes:
- Finding groups or ledger rows addressed:

## Scope

- In scope:
- Out of scope:
- Expected files/modules touched:
- QR slice spec path (when present):
- Drift check command (when present):

## Batches

| Batch | Cluster | Evidence source | Expected edits | Verification | Stop condition | Status |
|---|---|---|---|---|---|---|
| 1 |  | slice-spec or QR scan |  |  | QR STOP conditions | pending |

## Execution Rules

- Work one coherent cluster at a time.
- Prefer the slice spec's scope and STOP conditions when present.
- Prefer current scanner or gate evidence over stale line numbers.
- Preserve pre-existing dirty work.
- Do not commit `.quality-runner/` artifacts unless already tracked.
- Do not mix unrelated finding families in one batch.
- If a batch exposes a real correctness bug, fix it only when it is local to
  the same cluster; otherwise record it as the next batch or a blocker.

## Verification Ladder

- Focused checks:
- Scanner or QR proof:
- Repo/package gates:
- Final rerun:

## Completion Criteria

- QR status target:
- Ledger target:
- Remaining accepted blockers:
```

## Batch Loop

For each batch:

1. Select the next cluster from current QR evidence, scanner output, or the
   phase ledger. Prefer high-yield clusters with shared cause, file ownership,
   or verification.
2. Read the affected files before editing.
3. State the intended edit pattern and why it preserves behavior.
4. Make the smallest coherent code change.
5. Run focused verification first.
6. Run scanner or QR proof for the exact finding family.
7. Update the phase ledger only for findings proven fixed, accepted, stale,
   superseded, or blocked with evidence.
8. Add or update a batch summary with commands and results.
9. Commit the coherent batch when source files changed and verification passed.
10. Push when the branch is expected to be shared or the run is long-lived.

## Batch Summary Template

```md
# Batch <number>: <name>

## Scope

- Files changed:
- QR findings or ledger rows addressed:
- Related blockers:

## Changes

- TBD

## Verification

| Command | Result |
|---|---|
|  |  |

## QR / Scanner Result

- Previous count:
- Current count:
- Rows fixed:
- Rows left unresolved:

## Blockers

- TBD

## Commit

- Commit:
- Push status:
```

## Ordering Rules

Use this default order unless the user gives a different priority:

1. Dependency setup, environment, and read-only policy blockers.
2. Failing executable gates.
3. Missing repo-owned gates.
4. High-signal correctness, safety, and type hardening findings.
5. High-yield structural clusters by file or rule family.
6. Broad cleanup and style-only work.

## Final Report

When stopping, report:

- QR run ids compared
- Final QR status and classification
- Handoff path
- Phase and batch artifacts updated
- Files changed
- Verification commands and results
- Commit hashes and push status
- Remaining blockers or next recommended phase
