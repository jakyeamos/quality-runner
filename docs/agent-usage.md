# Agent Usage

Quality Runner gives agents evidence and a handoff. The agent still owns the
work plan. For large or repo-wide remediation, agents should convert the QR
handoff into GSD-style phases and execute one coherent batch at a time.

## Start With QR

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
checkout rather than a sandbox.

Then read:

- `/path/to/repo/.quality-runner/exports/qr-handoff.md`
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

For a single slice, prefer the matching `slice-specs/*.md` file as the
execution contract. Use `remediation-plan.json` for ordering across slices and
`agent-handoff.md` for controller routing. Convert to GSD-style phase plans only
when the remediation spans multiple slices or needs repo-local planning history.

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
