# Integration Boundaries

Quality Runner is the evidence layer. It inspects repositories, records
findings and quality-gate evidence, groups remediation clusters, and compares
one QR run with another. It remains local-only, read-only, and advisory.

A planning or execution system is a separate consumer. It owns roadmap
structure, task ownership, execution state, commits, and implementation. QR
does not require or create `.planning/`, phase numbers, roadmap files, issue
records, or agent-specific state.

The stable handoff for any consumer is the artifact set in
`.quality-runner/runs/<run-id>/`:

- `quality-audit.json` for normalized evidence-backed findings
- `remediation-plan.json` for ordered, cluster-oriented recommendations
- `agent-handoff.json` for controller routing and gate state
- `slice-specs/` for cold-executor scope and verification contracts
- `remediation-delta.json` and `remediation-delta.md` when comparing runs

Use the QR-native refresh loop first:

```bash
quality-runner refresh /path/to/repo \
  --run-id-prefix qr-current \
  --baseline-run-id qr-baseline \
  --json

quality-runner remediation-delta /path/to/repo \
  --run-id qr-current-verify \
  --baseline-run-id qr-baseline-verify \
  --json
```

The delta is an update to evidence, not an instruction to rewrite a project
plan. A consumer decides how to represent it:

- GSD can map clusters to phases and update `PLAN.md` and `STATE.md`.
- An issue tracker can map clusters to work items.
- Another agent can use the Markdown or JSON contract directly.
- A human can review the delta without adopting a planning framework.

The GSD workflow documented in the agent guide is therefore an optional
adapter pattern for repositories that choose GSD. It is not part of QR's core
command or artifact contract.
