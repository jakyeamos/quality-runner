---
name: quality-runner
description: Run standalone audit, planning, and task-scoped prevention for a repository, producing authoritative quality evidence without modifying source files.
---

# Quality Runner

Use this skill when the user asks to audit a repository against quality
standards, run Quality Runner, inspect available quality gates, produce a
remediation plan, or prevent new trusted findings during implementation.

Quality Runner's preferred journeys are outcome-first. The canonical executable
is `qr`; `quality-runner` remains a compatible alias. Confirm the install with
`qr doctor --json`, then choose `audit`, `review`, `verify`, or `runs`. They
write local `.quality-runner/` evidence as needed but do not modify target
source files. Discovered gates remain evidence-only unless a user explicitly
authorizes `--execute-gates --worktree-mode disposable`; that runs local
commands in a disposable checkout, not a sandbox.

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

For `structural:improve-tests` findings, read `suggested_disposition`,
`disposition_rationale`, and `evidence_needed` before changing the suite. QR's
`merge`, `rewrite`, and `delete_candidate` values require an author decision;
they are review evidence, not permission to mutate tests. Do not add an
absence-only tombstone when behavior is intentionally removed. Delete tests,
fixtures, snapshots, and helpers whose sole contract disappeared, and create
new coverage only if a requested restoration or another durable contract
creates a real accidental-failure path.

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
qr doctor --json
qr audit /path/to/repo --run-id qr-<date-or-task> --json
qr review /path/to/repo --mode blind --run-id review-<date-or-task> --json
qr verify /path/to/repo --run-id qr-<date-or-task>-verify --json
qr runs /path/to/repo --json
```

For the four journey commands, read the
`quality-runner-outcome-v0.2` fields (`state`, `assessment`, evidence, writes,
safety, and `next_action`) instead of treating exit code `0` as a clean result.
When a task names a file below QR's default exclusions, use
`--include-path` for a bounded scan or `--include-ignored-path` to preserve the
rest of the scan, then inspect `scan_inclusions`. Use module-scoped
`--scan-exclusion-module` when security coverage must remain; protected paths
stay fail-closed.

Use `refresh` for the combined inspect/run/verify/handoff workflow and its
intent/review-cycle delta loop; read the resulting `review-delta.json` and
`review-delta.md`. Use `gate`/`gate-status`/`gate-respond` for controller
decisions, `review-worker` plus strict report validation for worker handoffs,
`plan`/`phase` or delivery contracts for bounded planning, `rollout` for
isolated multi-repository runs, `fleet detector refresh` for full exact-target
skill-pack evidence publication consumed by Pronto, and `release-smoke` before
release. The full agent protocol is in `docs/agent-usage.md`. Before publishing, build both
distributions and run `release-boundary REPOSITORY --dist-dir DIST --json`.
Treat `public_core`, `public_adapter`, and `local_only` as the exhaustive
distribution classes; public adapters require sanitized contract fixtures, and
local-only Pronto, fleet, account, or machine wiring must not enter artifacts or
the tracked public source tree. Require the persisted
`quality-runner-release-boundary/v2` receipt to match the exact release branch
and commit; legacy, stale, dirty, or blocked receipts are not release evidence.

Use `qr fleet detector refresh --all --projects-root ROOT --json` only when the
operator explicitly wants repository-local detector evidence refreshed. It
scans disposable exact-target worktrees with full deterministic skill packs,
does not execute discovered gates, and publishes normal QR runs into each
repository for Pronto. Add `--anti-slop-root PINNED_CHECKOUT` to enable the
explicit pinned Anti-Slop adapter for compatible JavaScript/TypeScript
repositories. The adapter consumes the producer's JSON or SARIF output,
records exact provenance and cache identity, relates overlapping native QR
findings, and blocks malformed or failed external evidence. Inspect the
per-repository `published`, `blocked`, and `unsupported` results before running
`pronto quality refresh --json`.

For planning and execution loops, use the additive delivery contract surface:

```bash
qr plan contract prepare /path/to/repo --phase-id phase-1 --plan-id plan-1 --json
qr plan contract refresh /path/to/repo --contract CONTRACT --json
qr plan preflight /path/to/repo --contract CONTRACT --plan-file PLAN.md --json
qr plan reconcile /path/to/repo --contract CONTRACT --result-file delivery-result.json --json
```

Contract preparation and refresh use balanced analysis with an external cache by
default. Preflight reads existing contract and plan artifacts without rescanning;
reconcile consumes one structured result per execution plan or batch. Use full
analysis at phase, release, or audit boundaries. Hard obligations, stale source
fingerprints, missing mandatory evidence, uncovered plan obligations, and
deferred hard checks block reconciliation; advisory obligations remain visible.

Audit and remediation workflow:
For fleet audits, automatic discovery honors the projects-root
`.quality-runner/fleet.json` exclusion policy and records it in inventory.
Dynamic checks always target a committed ref in a detached disposable worktree;
a dirty source checkout is an eligible host because QR fingerprints it before
and after and blocks the result if anything changes. Safe configured `pre_cr`
aggregates and the exact read-only `docker compose ... config` form are eligible
for dynamic execution; dependency install, synchronization, and unpinned
`uv --with` commands remain blocked.
An alternate checkout may donate a JavaScript dependency tree only when its
package-manager declaration, dependency fields, and lockfile signature match
the detached target.

Use `qr fleet audit run --all --standard cache-design --json` for a read-only
derived-storage maturity slice. Inspect its private `standard-report.json`; do
not publish a standard-scoped snapshot as the canonical feed. The detector does
not execute cleanup or repository commands, raw size alone is not a failure,
and unknown traversal evidence must remain unknown.

Agent workflow:

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
