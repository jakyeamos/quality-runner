---
name: quality-runner
description: Run standalone audit, planning, and task-scoped prevention for a repository, producing authoritative quality evidence without modifying source files.
---

# Quality Runner

Use this skill when the user asks to audit a repository against quality
standards, run Quality Runner, inspect available quality gates, produce a
remediation plan, or prevent new trusted findings during implementation.

Quality Runner's preferred journeys are outcome-first. They write local
`.quality-runner/` evidence as needed but do not modify target source files.
Discovered gates remain evidence-only unless a user explicitly authorizes
`--execute-gates --worktree-mode disposable`; that runs local commands in a
disposable checkout, not a sandbox.

Preferred MCP tools:

- `quality_runner_audit_outcome` to inspect or plan with a clear remediation outcome.
- `quality_runner_review_outcome` to distinguish a completed review from a packet awaiting evidence.
- `quality_runner_verify_outcome` to record or explicitly authorize disposable verification.
- `quality_runner_runs_outcome` to read persisted run history without writing a summary.

Use the legacy MCP tools only when an existing client requires their v1 payloads.

## Implementation completion contract

For an implementation task, capture the baseline before source edits:

```bash
qr task start /path/to/repo --task-id <stable-task-id> --json
```

During editing, use only repository-native checks whose current applicability
and maturity are established by repository evidence. Do not infer that a
command is preventative merely because it appears in a manifest or CI file.
Candidate QR gates remain advisory and are not executed by `qr task check`.

After editing, run the authoritative QR checkpoint before declaring the
implementation complete:

```bash
qr task check /path/to/repo --task-id <stable-task-id> --json
```

Interpret the result as follows:

- `pass` permits completion only after any other repository-required checks pass.
- `violation` requires fixing or explicitly disposing every new enforced
  finding and failed certified gate, followed by another task check.
- `blocked` is unknown evidence, never a pass. Resolve its blockers and rerun.
- `invalid` requires correcting the invocation or prevention configuration.

Read the emitted `task-check.json` as the authority and `task-check.md` as its
human projection. Persisted legacy and advisory findings remain visible but do
not become task failures. Do not copy every QR finding into static agent rules;
promote a repeatedly trusted deterministic finding into a behavior-verified QR
rule or a faster native checker with its own maturity evidence.

This is a baseline and completion/CI checkpoint, not a continuous-save or
editor-hook workflow. Re-run it after correcting violations or blockers. Use
`qr task rebaseline --reason ...` only when configuration, policy, rule-pack,
QR version, or toolchain evidence genuinely changed; never enlarge a baseline
silently.

Fresh Review is two phase: first prepare the packet, then submit a locally
supplied response bound to that packet. A packet-ready outcome is not a clean
review. Select findings explicitly before giving its fixer prompts to a separate
agent; Quality Runner does not apply those fixes.

CLI fallback:

```bash
quality-runner audit /path/to/repo --run-id qr-<date-or-task> --json
quality-runner verify /path/to/repo --run-id qr-<date-or-task>-verify --json
quality-runner runs /path/to/repo --json
```

For planning and execution loops, use the additive delivery contract surface:

```bash
quality-runner plan contract prepare /path/to/repo --phase-id phase-1 --plan-id plan-1 --json
quality-runner plan contract refresh /path/to/repo --contract CONTRACT --json
quality-runner plan preflight /path/to/repo --contract CONTRACT --plan-file PLAN.md --json
quality-runner plan reconcile /path/to/repo --contract CONTRACT --result-file delivery-result.json --json
```

Contract preparation and refresh use balanced analysis with an external cache by
default. Preflight reads existing contract and plan artifacts without rescanning;
reconcile consumes one structured result per execution plan or batch. Use full
analysis at phase, release, or audit boundaries. Hard obligations, stale source
fingerprints, missing mandatory evidence, uncovered plan obligations, and
deferred hard checks block reconciliation; advisory obligations remain visible.

Audit and remediation workflow:

1. Run QR before editing source.
2. Read `.quality-runner/runs/qr-<date-or-task>/agent-handoff.md` and the referenced artifacts from that run.
3. Before editing, write or update GSD-style planning artifacts in the target repo.
   Use the repo's existing planning folder if present; otherwise use `.planning/`.
4. The plan must include phases, batches, evidence, expected touched files,
   verification commands, stop conditions, and expected QR/scanner improvement.
5. Execute one coherent batch at a time. Do not mix unrelated QR finding families.
6. After each batch, run focused verification, run QR or scanner proof when practical,
   update the phase ledger/summary, then commit the coherent change set if source changed.
7. Do not commit `.quality-runner/` artifacts unless the repo already tracks them.
8. Preserve pre-existing dirty work.

For the planning template, follow `docs/agent-usage.md` in the Quality Runner repo.
