# Planning and Delivery Contracts

Quality Runner can sit in a planning loop without turning every plan check into
a repository refresh. The contract surface is additive and remains disabled in
GSD and Terrace until the performance gate passes.

## Performance-first analysis

Use `--analysis-mode balanced` for planning and incremental verification. It
analyzes changed and relevant surface paths, reuses unchanged per-file results,
and records global checks that were deferred. Use `--analysis-mode full` for
phase completion, release readiness, and audits.

Cache persistence is explicit:

- `repo` writes normal refresh caches under `.quality-runner/cache/`.
- `external` reads and writes a cache outside the target checkout. It is the
  default for planning contracts and leaves no target-repository cache state.
- `disabled` performs a diagnostic run without reading or writing analysis
  cache state.

Each run writes `performance.json` with phase timings, traversal metrics, bytes
read, cache hits and misses, recomputed files, cache-index writes, deferred
checks, timeout reasons, the current phase, and an exact resume command when a
budget is exceeded. Partial evidence is explicitly marked partial; it is not
reported as a complete assurance scan.

## Contract lifecycle

Prepare a contract before research:

```bash
quality-runner plan contract prepare /path/to/repo \
  --phase-id phase-1 --plan-id plan-1 --intent "Implement the phase" --json
```

Refresh it after research or context. Refresh creates a new immutable contract
and records the previous contract id:

```bash
quality-runner plan contract refresh /path/to/repo \
  --contract /path/to/repo/.quality-runner/runs/<run-id>/delivery-contract.json \
  --context-ref .planning/phases/01-feature/CONTEXT.md \
  --research-ref .planning/phases/01-feature/RESEARCH.md --json
```

Preflight consumes the saved contract and a native plan. It reads the plan
file, but does not rescan the repository or launch another QR refresh:

```bash
quality-runner plan preflight /path/to/repo \
  --contract /path/to/repo/.quality-runner/runs/<run-id>/delivery-contract.json \
  --plan-file .planning/phases/01-feature/01-01-PLAN.md --json
```

Reconcile one structured delivery result per execution plan or batch:

```bash
quality-runner plan reconcile /path/to/repo \
  --contract /path/to/repo/.quality-runner/runs/<run-id>/delivery-contract.json \
  --result-file delivery-result.json --json
```

Hard obligations, stale fingerprints, missing mandatory evidence, missing plan
coverage, and deferred hard checks block. Advisory and heuristic obligations
remain visible without blocking.

The same operations are available through the MCP tool
`quality_runner_delivery_contract` with `operation` set to `prepare`,
`refresh`, `preflight`, or `reconcile`.

## Integration boundary

GSD and Terrace integrations are opt-in. Their native planning and execution
fields remain authoritative: QR obligations map into GSD `must_haves`, task
acceptance criteria, verification commands, and stop conditions, while Terrace
keeps its RED/GREEN, senior-cycle, state, and GSD-alias behavior.

QR remains source-read-only. It does not install dependencies, edit source, or
execute project gates automatically. The QR Python project uses `pnpm` only for
JavaScript development commands where applicable; Terrace may report its own
legacy `npm` command surface. The adapter records that package-manager conflict
for review and never silently rewrites either repository's commands.
