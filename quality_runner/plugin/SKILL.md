---
name: quality-runner
description: Run standalone audit-and-plan quality orchestration for a repository, producing evidence-backed remediation plans without modifying source files.
---

# Quality Runner

Use this skill when the user asks to audit a repository against quality standards, run Quality Runner, inspect available quality gates, or produce a remediation plan.

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
