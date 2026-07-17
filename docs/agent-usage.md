# Agent Usage

Quality Runner gives agents evidence, a handoff, and an optional native phase
workflow. QR owns the phase documents and evidence progression, while the
agent or human still owns source edits, verification command execution, and
git operations. For large or repo-wide remediation, use one coherent batch at
a time.

## Invocation

The examples below use `quality-runner` for readability. Consumer repositories
should use the source-first contract in [Consumer Tooling](consumer-tooling.md):
`uvx --refresh --from git+https://github.com/jakyeamos/quality-runner.git
quality-runner ...` for latest QR, or `uv run --project /path/to/quality-runner
quality-runner ...` for a specific checkout.

## Command Selection Contract

Choose the command from the proof the task needs, not from the command that is
most familiar. Use the most specific matching row; release readiness takes
precedence over review, implementation, audit, and discovery:

| Needed proof | Entry command | Do not treat it as |
| --- | --- | --- |
| Target release, publish, upgrade, version/tag, artifact, CI provenance, migration/cutover, staging, or publication readiness | `quality-runner verify-gates <repo> --profile release --ci-status-json <repo>/.quality-runner/ci-status.json --readiness-evidence-file <repo>/.quality-runner/release-evidence.json --worktree-mode disposable --read-only-gates --json` | A normal gate run or source-test result |
| Implement or remediate a task and produce a handoff | `quality-runner refresh <repo> --run-id-prefix <task> --handoff-output <handoff>.md --json` | Release readiness |
| Perform a second-pass task-aware review | `quality-runner review <repo> --task "<task>" --json` | A remediation command |
| Review without task context | `quality-runner review <repo> --mode blind --json` | Task-scoped review |
| Discover repository facts only | `quality-runner inspect <repo> --json` | A quality pass |
| Produce audit findings and a plan without executing repo gates | `quality-runner run <repo> --run-id <run> --json` | Gate verification |
| Verify Quality Runner's own installed/public package surfaces | `quality-runner release-smoke --json` | The target repository's release profile |

The release row requires current-head CI evidence and a validated release
evidence file. If the repository is dirty, do not add
`--allow-dirty-worktree-verify` unless the user explicitly accepts verification
against dirty source; use a clean disposable worktree otherwise.

Do not substitute one command for another:

- `inspect` is discovery only; it does not audit or verify gates.
- `run` writes an audit and plan; it does not execute discovered gates.
- `refresh` uses the selected profile, but its default profile is not release
  readiness. Add `--profile release` when the release row applies.
- `verify-gates` without `--profile release` does not prove target release
  readiness.
- `release-smoke` checks Quality Runner's own package and public surfaces; it
  does not replace target-repository release evidence.

For workflow commands, use `--json` and inspect `status`, `lifecycle_status`,
`blockers`, `gate_verification`, and `readiness` before proceeding. A zero exit
code means the command completed; it does not by itself mean the repository is
merge-ready. Never continue from `gates-blocked`, `gates-failed`, unresolved
readiness, stale provenance, or missing evidence.

## Active Skill Pack Contract

Quality Runner also discovers a user-level compiled corpus from
`~/.config/quality-runner/quality-runner.toml` or `QUALITY_RUNNER_GLOBAL_CONFIG`.
It selects relevant packs from repository signals and records every decision in
`code-quality-scan.json`. Local packs remain compatible and take precedence over
global packs with the same id. Deterministic rules are evaluated during the
scan. When an active pack contains `agent_reviews`, QR writes
`skill-review-packet.json` and `skill-review-packet.md` and adds a `skill_review`
object to the handoff.

Agent review execution is an asynchronous sidecar to QR. Select its policy with
`--agent-review-mode`:

- `auto` (the default): emit the packet and route it to the supervising agent
  as an automatic work item. The agent should inspect every active rubric,
  record evidence-backed outcomes, and rerun QR with the validated report;
  users do not triage ordinary subjective observations.
- `parallel`: explicit sidecar review. The handoff reports
  `skill_review.status = review-pending`; this does not block deterministic QR
  completion.
- `required`: keep unresolved reviews as `review-required` blockers. The
  `release` profile selects this mode automatically, even when `off` or
  `parallel` was requested.
- `off`: do not emit review packets and report `skill_review.status = not-run`.

The agent owns the judgment step. When `skill_review.status` is
`review-required`, `review-pending`, or `review-rejected` and a review is needed:

1. Read the packet and inspect its scoped files against every rubric.
2. Write a report using `quality-runner-skill-review-report-v0.1` with concrete
   file, line, and evidence fields. Include `reviewed_review_ids` for every
   active skill/review pair, even when the review has no finding.
3. Rerun the same QR workflow with `--skill-review-report <report.json>`.
4. Continue only when the handoff reports `skill_review.status = reviewed`.

In `required` mode, do not report a clean, gates-clean, or merge-ready result
while the review remains unresolved. In `auto` mode, treat `review-pending` as
an automatic next action for the supervising agent. In `parallel` mode, treat
`review-pending` as incomplete review work even though deterministic QR gates
may continue.
QR remains local-first and non-executable: it creates the packet and validates
the report, while the supervising agent performs the repository review.

## Start With QR

Run QR before editing:

```bash
quality-runner refresh /path/to/repo \
  --run-id-prefix qr-<date-or-task> \
  --handoff-output /tmp/qr-handoff.md \
  --json
```

Then read:

- `/tmp/qr-handoff.md`
- `.quality-runner/runs/<run-id>/slice-specs/<next-slice-id>.md` for the
  cold-executor plan on the queued slice (scope, STOP conditions, drift check,
  evidence excerpts)
- `.quality-runner/runs/<run-id>/quality-audit.json`
- `.quality-runner/runs/<run-id>/remediation-plan.json`
- `.quality-runner/runs/<run-id>/gate-verification.json`, when present
- `.quality-runner/runs/<run-id>/code-quality-scan.json`, when structural
  findings drive the work
- intent docs listed in the handoff (`PRODUCT.md`, `DESIGN.md`, ADRs, etc.)

Do not edit source before reading the handoff and the relevant artifacts.

The default remediation view is domain-oriented. Start with
`remediation-plan.json.phase_candidates` or the matching section in
`agent-handoff.md` to choose a coherent workstream. Follow each candidate's
`slice_ids` to the leaf slices and `slice-specs/` before dispatching bounded
work. The plan's `slices` list remains the forensic, per-file/per-finding view;
use it when a candidate needs to be decomposed or investigated more narrowly.

For a single slice, prefer the matching `slice-specs/*.md` file as the
execution contract. Use `remediation-plan.json` for ordering across slices and
`agent-handoff.md` for controller routing. The executor or planning system
chooses its own representation for work items; QR does not require GSD or
repo-local `.planning/` files.

After package, lockfile, configuration, or source changes, rerun QR against a
known baseline and compare the evidence:

```bash
quality-runner refresh /path/to/repo \
  --run-id-prefix qr-after-update \
  --baseline-run-id qr-before-update \
  --json
quality-runner remediation-delta /path/to/repo \
  --run-id qr-after-update-verify \
  --baseline-run-id qr-before-update-verify \
  --json
```

Use `remediation-delta.json` or `.md` to update the chosen planning system.
Keep ownership, design decisions, and plan structure in that system. Do not
ask QR to rewrite its files.

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

## Native QR Phase Workflow

Initialize the QR-owned namespace after the first useful run:

```bash
quality-runner plan auto /path/to/repo --run-id qr-baseline-run --json
quality-runner phase next /path/to/repo --phase 1 --json
```

`phase plan` can consume a run or an existing `agent-handoff.json`. When the run
contains domain `phase_candidates`, QR plans one native phase plan per domain;
older artifacts without that field continue to use their leaf slices. Each
plan has source references, scope, tasks, stop conditions, verification gates,
dependencies, and a deterministic wave. QR dispatches the next ready plan but
does not execute it.

After an external batch, write a result file using the
`quality-runner-phase-batch-result-v0.1` schema and record it:

```bash
quality-runner phase record-batch /path/to/repo \
  --phase 1 --plan 1 --result-file batch-result.json --json
quality-runner phase update /path/to/repo \
  --phase 1 --baseline-run-id qr-before --run-id qr-after --json
quality-runner phase verify /path/to/repo --phase 1 --run-id qr-after --json
```

When every plan is verified, close the phase:

```bash
quality-runner phase close /path/to/repo --phase 1 --run-id qr-after --json
```

Native planning files live only under `.planning/quality-runner/`. QR does not
modify root GSD files, import or export GSD state, run source changes, commit,
or push.

## Optional External Planning Systems

Before changing code, the executor must record a bounded work item using the
native QR phase workflow or another planning mechanism. If the repository uses
GSD, the following layout remains a valid independent consumer choice:

```text
.planning/
  STATE.md
  phases/
    <phase-number>-<slug>/
      PLAN.md
      RESOLUTION-LEDGER.tsv
      <batch-number>-SUMMARY.md
```

These files are GSD-owned planning artifacts, not QR-owned output. Other
planning systems can use the same QR artifacts without adopting this layout.

## Optional GSD Adapter Template

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
