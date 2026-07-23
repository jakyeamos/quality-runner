# Quality Runner context index

last_reviewed: 2026-07-22

Read this index after [AGENTS.md](../../AGENTS.md). Load one packet for the
task; do not recursively load the repository or every context packet.

## Stable references

- [Project README](../../README.md): product purpose and user-facing journeys.
- [Project truth](../../.tracker/PROJECT_TRUTH.md): current branch, release,
  verification, and known risks.
- [Contribution guide](../../CONTRIBUTING.md): contributor expectations.
- [Security policy](../../SECURITY.md): artifact and disclosure boundaries.

## Route by task

| When the task involves | Read |
| --- | --- |
| package boundaries or ownership | [architecture.md](architecture.md) |
| setup, commands, or quality gates | [commands.md](commands.md) |
| Python style or compatibility | [conventions.md](conventions.md) |
| credentials, network, or sensitive artifacts | [security.md](security.md) |
| failure recovery or stale evidence | [failure-modes.md](failure-modes.md) |
| examples or reusable patterns | [examples.md](examples.md) |
| definition of done or acceptance | [done.md](done.md) |
| release, deployment, or rollback | [deployment.md](deployment.md) |

## Minimum context

Start with the relevant packet and current truth. Read source modules only after
the packet identifies the owner and boundary. If evidence is missing or stale,
report that state and repair the evidence contract before making a claim.
