# Semantic Invariants

Semantic invariants turn a confirmed repository-specific regression into a
durable, executable Quality Runner contract. They are intentionally narrower
than generic static-analysis rules: the repository owns the behavior statement,
proof surfaces, command, and enforcement level.

```toml
[[quality_runner.invariants]]
id = "human-only-review-not-reusable"
description = "Handoff-only prompts never enter the reusable answer queue."
owner = "application-review-classifier"
surfaces = [
  "queue-ui.mjs",
  "apply/question-ledger.mjs",
  "tests/queue-ui-payload.test.mjs",
]
command = "node --test tests/queue-ui-payload.test.mjs"
enforcement = "advisory"
ecosystem = "javascript"
mutating_risk = "safe"
freshness_days = 30
```

IDs must be stable kebab-case names. Surface and evidence paths must be safe,
repository-relative paths. A command or `evidence_file` is required. Commands
follow the normal Quality Runner execution boundary: discovery is read-only,
and local execution requires `--execute-gates --worktree-mode disposable`.

## Status and enforcement

Every run writes `invariant-verification.json`. Each invariant receives one of:

- `passed`: the current command passed, or fresh evidence records a pass.
- `failed`: the current command ran and disproved the invariant.
- `blocked`: the environment or prerequisite prevented a trustworthy result.
- `unknown`: proof is missing, invalid, or was not executed.
- `stale`: the configured evidence is older than `freshness_days`.

`advisory` is the default and cannot block the repository result. Promote an
invariant to `required` only after the command is deterministic and the proof
surfaces are stable. Reusable candidate promotion also requires the governed
fleet evidence and human receipt described in
[Bug-learning lifecycle](bug-learning.md). A required failure fails verification; required
`blocked`, `unknown`, or `stale` evidence blocks verification without claiming
the behavior failed.

An optional evidence file uses this machine-readable contract:

```json
{
  "schema": "quality-runner-invariant-evidence-v0.1",
  "id": "human-only-review-not-reusable",
  "status": "passed",
  "checked_at": "2026-07-29T14:00:00Z"
}
```

## Promotion rule

Use the smallest durable scope:

1. Reproduce the defect and add a repository regression test.
2. Register it as an advisory semantic invariant.
3. Record classified, costed observations in the candidate registry.
4. Aggregate independent repository evidence.
5. Obtain an explicit human promotion decision.
6. Promote it to required only when the promotion receipt is supported.

Do not add one-off symptoms, generic corpus examples, or flaky end-to-end
checks. The invariant should express a repeated architectural boundary with a
cheap, owned proof.
