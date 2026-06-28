---
name: quality-runner
description: Run standalone audit-and-plan quality orchestration for a repository, producing evidence-backed remediation plans without modifying source files.
---

# Quality Runner

Use this skill when the user asks to audit a repository against quality standards, run Quality Runner, inspect available quality gates, or produce a remediation plan.

Quality Runner v1 is audit-and-plan only. It writes `.quality-runner/` artifacts and does not modify target source files.

Preferred MCP tools:

- `quality_runner_inspect_repo` to inspect repo shape and quality capabilities.
- `quality_runner_run` to write the full audit, remediation plan, and agent handoff.
- `quality_runner_status` to list existing runs.
- `quality_runner_export_handoff` to read an existing `agent-handoff.md`.

CLI fallback:

```bash
quality-runner run /path/to/repo --standards jakyeamos --json
```
