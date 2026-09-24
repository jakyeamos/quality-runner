---
id: quality-runner.repo-context
title: Quality Runner Repository Context
tier: project
status: active
last_reviewed: 2026-08-26
applies_when:
  - repo_context
tags:
  - python
  - quality-orchestration
  - local-first
---

# Quality Runner context index

Read this index before non-trivial repository work. Route to the smallest
packet that matches the task; do not load the whole repository or generated
`.quality-runner/` artifacts into context.

| Task evidence | Read |
| --- | --- |
| Architecture and ownership boundaries | [architecture](architecture.md) |
| Commands and quality gates | [commands](commands.md) |
| Python and artifact conventions | [conventions](conventions.md) |
| Security, credentials, and approval gates | [security](security.md) |
| Failure diagnosis and recovery | [failure modes](failure-modes.md) |
| Canonical implementation examples | [examples](examples.md) |
| Definition of done | [done](done.md) |
| Packaging, release, and rollback | [deployment](deployment.md) |
| Public CLI or MCP behavior | `docs/cli.md`, `quality_runner/cli.py`, `quality_runner/cli_task.py`, `quality_runner/task_prevention.py`, `quality_runner/task_contract.py`, `quality_runner/mcp.py` |
| Quality-gate execution behavior | `docs/cli.md`, `quality_runner/gate_execution.py`, `quality_runner/verification_contract.py` |
| Artifact or schema changes | `docs/artifacts.md`, `quality_runner/task_contract.py`, `quality_runner/schemas/`, `tests/` |

The runner is provider-neutral and AIOS-independent. Generated evidence may
contain sensitive repository details; it remains local unless a human reviews
and explicitly publishes a redacted projection.

The executable environment contract validates this index's links and freshness,
the certified type-checking setting, the locked quality ladder, CI and release
coverage, Quality Runner blocker gates, and secret-file ignore protections.
Refresh this index when command, quality-adapter, or release-boundary behavior
changes. Strict type-checking findings are remediation work; they must remain
visible rather than being suppressed.
