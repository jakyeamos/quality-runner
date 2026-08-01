# Agent Usage

Quality Runner gives agents evidence and a handoff. QR can also maintain an
advisory native phase plan; the external agent or human still owns source
changes, commits, pushes, and execution decisions.

## Invocation

The examples below use `quality-runner` for readability. Consumer repositories
should use the source-first contract in [Consumer Tooling](consumer-tooling.md):
`uvx --refresh --from git+https://github.com/jakyeamos/quality-runner.git
quality-runner ...` for latest QR, or `uv run --project /path/to/quality-runner
quality-runner ...` for a specific checkout.

## Prevent Findings During Implementation

Use the task workflow at meaningful evidence boundaries:

| Boundary | Required behavior |
| --- | --- |
| Before source edits | Capture one task baseline. |
| During editing | Use applicable repository-native checks whose current maturity is established. |
| Before completion | Run the authoritative `qr task check`. |
| After a violation or blocker | Correct the cause and rerun the task check. |
| Pull request | Use an immutable target revision as the baseline. |
| Nightly or rule-pack change | Run the full repository audit for debt visibility and reconciliation. |

The task check is deliberately not required on every save. Agent instructions
guide implementation behavior; they do not replace QR's baseline, coverage,
matching, readiness, or policy evidence. Do not translate every advisory
finding into a static prohibition. Promote a repeatedly trusted deterministic
finding into a behavior-verified QR rule or a faster native checker, with
positive, negative, ambiguous, local, and CI evidence appropriate to that
capability.

For ordinary implementation work, capture the task baseline before editing:

```bash
qr task start /path/to/repo --task-id <stable-task-id> --json
```

After editing and before declaring the implementation complete:

```bash
qr task check /path/to/repo --task-id <stable-task-id> --json
```

Fix new enforced findings and failed certified gates. Do not treat persisted
legacy debt as a task failure, and do not interpret `blocked` as a pass. When
configuration, rule packs, promoted policy, the toolchain, or the QR version
changes, review that change and use `task rebaseline --reason ...`; never
silently enlarge the baseline. PR-target tasks preserve the originally resolved
target SHA across rebaseline.

Read `task-check.json` as the canonical result and `task-check.md` as its human
projection. The emitted `next_action` explains the required response for
`pass`, `violation`, `blocked`, or `invalid`; a passing QR result still does not
waive other repository-required checks.

Do not assume a fast native check is mature enough for this loop. QR executes
only gates whose prevention configuration includes the required bootstrap,
tool provenance, repeatability, intentional-failure, local, and CI evidence.
Required but uncertified or unavailable gates block the check. Candidate gates
stay advisory.

QR owns evidence and policy evaluation only. The implementing agent still owns
source changes and decides how to correct a violation; QR does not edit code,
drive the agent, install prerequisites, commit, or push.

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
