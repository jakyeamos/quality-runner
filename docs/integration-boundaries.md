# Integration Boundaries

Quality Runner is the evidence layer. It inspects repositories, records
findings and quality-gate evidence, groups remediation clusters, and compares
one QR run with another. It remains local-only, read-only, and advisory.

A planning or execution system can be a separate consumer, or QR can own its
native phase documents. QR's native planning layer owns roadmap structure,
cluster plans, wave/dependency metadata, dispatch state, batch summaries, and
evidence verification under `.planning/quality-runner/`. It still does not own
task execution, source changes, commits, or pushes.

QR never imports or updates existing GSD files. `.planning/ROADMAP.md`,
`.planning/STATE.md`, and GSD phase directories remain independent. GSD and
other planning systems can consume the canonical QR artifacts directly.

Consumers should invoke QR through the source-first contract in
[Consumer Tooling](consumer-tooling.md), not through a copied package or an
unverified global binary.

## GitHub Actions failure prompt bridge

This repository also has an optional `.github/workflows/codex-ci-prompt.yml`
consumer workflow. It listens for completed `CI` runs whose conclusion is
`failure`, `cancelled`, `timed_out`, or `action_required`, then uses the
published `jakyeamos/ci-incident-router` action to create one bounded artifact
containing `codex-ci-prompt.json` and `codex-ci-prompt.md`.

The action is pinned to a verified bridge commit. The prompt workflow does not
check out the failed run's commit, execute pull-request code, modify source,
commit, push, comment, or start Codex. Logs, patches, workflow names, and pull
request text remain untrusted evidence; fork pull requests stay diagnosis-only.

The workflow must be present on this repository's default branch before
`workflow_run` can trigger it. A live pilot is complete only after a failed CI
run produces the artifact, the artifact contains exactly the two prompt files,
and the local bridge `download`/`consume` commands read it back successfully.

The stable handoff for any consumer is the artifact set in
`.quality-runner/runs/<run-id>/`:

- `quality-audit.json` for normalized evidence-backed findings
- `remediation-plan.json` for domain-oriented phase candidates with linked leaf
  remediation clusters
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
plan. The native QR lifecycle can consume it directly:

```bash
quality-runner plan auto /path/to/repo --run-id qr-current-run --json
quality-runner phase update /path/to/repo \
  --phase 1 --baseline-run-id qr-baseline-verify --run-id qr-current-verify --json
```

The native layer preserves human-authored context and task sections while
updating machine-owned status and evidence blocks. A consumer can still decide
to represent the delta another way:

- GSD can map domain candidates to phases, then use linked leaf slices to fill
  `PLAN.md` and `STATE.md` without losing forensic traceability.
- An issue tracker can map clusters to work items.
- Another agent can use the Markdown or JSON contract directly.
- A human can review the delta without adopting a planning framework.

The GSD workflow documented in the agent guide is therefore an optional
adapter pattern for repositories that choose GSD. It is not part of QR's core
command or artifact contract.
