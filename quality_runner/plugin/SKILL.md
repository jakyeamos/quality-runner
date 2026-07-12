---
name: quality-runner
description: Run standalone audit-and-plan quality orchestration for a repository, producing evidence-backed remediation plans without modifying source files.
---

# Quality Runner

Use this skill when the user asks to audit a repository against quality standards, run Quality Runner, inspect available quality gates, or produce a remediation plan.

Quality Runner v1 is audit-and-plan by default. It writes `.quality-runner/`
artifacts and does not modify target source files. Discovered gates are evidence
only unless a user explicitly authorizes `--execute-gates --worktree-mode
disposable`; that runs arbitrary local commands in a disposable checkout, not a
sandbox.

Preferred MCP tools:

- `quality_runner_inspect_repo` to inspect repo shape and quality capabilities.
- `quality_runner_run` to write the full audit, remediation plan, and agent handoff.
- `quality_runner_status` to list existing runs.
- `quality_runner_export_handoff` to read an existing `agent-handoff.md`.

CLI fallback:

```bash
quality-runner refresh /path/to/repo \
  --run-id-prefix qr-<date-or-task> \
  --handoff-output /path/to/repo/.quality-runner/exports/qr-handoff.md \
  --json
```

Agent workflow:

1. Run QR before editing source.
2. Read `.quality-runner/exports/qr-handoff.md` and the referenced `.quality-runner/runs/<run-id>/` artifacts.
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
