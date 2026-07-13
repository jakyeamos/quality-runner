# Modernization Audit

## Scope and baseline

This audit examines Quality Runner at commit `0a3def1` before modernization.
The audit did not change application behavior. The implementation work will take
place on `codex/gpt56-modernization`, leaving `main` intact for comparison and
rollback.

Quality Runner is a local-first developer tool: it gathers repository evidence,
plans remediation, and hands work to a separately authorized agent. Its product
is therefore its command flow, Markdown/JSON artifacts, and MCP contract—not a
browser interface. A conventional web redesign would add surface area without
improving the primary job.

## What must survive

- Local-first operation, explicit evidence limits, and no silent remote transfer.
- The separation between auditing/planning and source mutation.
- Versioned, human-readable and machine-readable artifacts under the target
  repository's Quality Runner state directory.
- Existing public scripts, MCP tools, JSON schemas, config semantics, and the
  compatibility namespaces until a published deprecation window has elapsed.
- Artifact path hardening, read-only verification safeguards, and worktree
  handling. These are product guarantees, not implementation details.

## Diagnosis

The repository has meaningful domain coverage and a substantial test suite, but
the system currently asks users to bridge several inconsistent promises:

| Area | Evidence | Why it matters |
| --- | --- | --- |
| Release identity | Project metadata declares 0.5.0 while runtime and plugin metadata declare 0.4.0 (`pyproject.toml`, `quality_runner/__init__.py`, and `quality_runner/plugin/manifest.json`). | A quality tool cannot make its own installed identity ambiguous; the wheel contract test fails as a result. |
| Safety boundary | `refresh` can pass target-repository commands to a shell, while the threat model says discovered commands are evidence only. The compatibility CLI also has unvalidated artifact output paths. | Local configuration is untrusted input. “Read-only” must not mean arbitrary execution with best-effort cleanup. |
| User outcome | Fresh Review can return `review-not-run` yet show the generic no-major-issues summary. | A packet awaiting a reviewer must never resemble a successful review. |
| Product navigation | The root CLI exposes implementation-level commands alongside common journeys; help and README make users choose a subsystem before they know the outcome they want. | The interface is cognitively expensive for the solo developer and agent-controller personas. |
| Architecture | Workflow orchestration, artifact persistence, dynamic dictionaries, and rendering are interleaved. `cli` and `cli_payload` have an import cycle. | New features multiply integration cost and make type guarantees weak at the boundaries that carry safety-critical data. |
| Compatibility | `repo_quality_certifier` is a large, installed compatibility surface that release smoke exercises. | Deleting it during a rewrite would be an unplanned public API break. |

## Baseline verification

The following commands were run against the baseline. Build artifacts were sent
to a temporary directory; no tracked source changes resulted.

| Check | Result |
| --- | --- |
| `uv run --offline --with pytest pytest -q` | Failed: 395 passed, 1 failed—the packaged wheel has 0.5.0 metadata but the runtime test expects the stale 0.4.0 version. |
| `uv run --offline --with ruff ruff check .` | Failed: three import-order findings in the CLI/payload/ledger surfaces. |
| `uv run --offline --with ruff ruff format --check .` | Failed: 15 files would be reformatted. |
| `uv run --offline --with basedpyright basedpyright` | Failed: 14 errors, concentrated in the Fresh Review typed-dictionary boundary. |
| `uv run --offline --with vulture vulture . --min-confidence 70` | Passed. |
| `uv build --offline --out-dir /tmp/quality-runner-baseline-build` | Passed: sdist and wheel built. |
| `quality-runner release-smoke --json` | Passed, but it does not compare wheel, runtime, MCP, and plugin version values. |

## Risk priorities

### P1 — fix before broad refactoring

1. Make artifact reads and writes use one symlink-safe, containment-checked
   resolver. Apply it to the primary and compatibility CLIs as well as MCP.
2. Treat verification as code execution: unknown target commands do not run by
   default; explicitly requested execution is isolated and receives a minimal
   environment.
3. Create one authoritative version value and verify it against package metadata,
   the built wheel, CLI, MCP, plugin metadata, docs, and distribution metadata.
4. Render `review-not-run` as a distinct “packet ready” outcome with an explicit
   next action, not a no-findings result.

### P2 — resolve through the new core

- Replace untyped cross-layer payloads with explicit input/output contracts.
- Separate deterministic analysis from artifact persistence and command adapters.
- Consolidate command UX around user journeys while retaining legacy command
  aliases for the compatibility window.
- Bound scanning and writes, make state updates atomic, pin CI dependencies, and
  make coverage claims match what CI measures.

## Scorecard

Scores describe the baseline and the approved target design, not a claim that
the target has already been implemented.

| Dimension | Current | Target | Rationale |
| --- | ---: | ---: | --- |
| Product coherence | 2 | 5 | Outcome-led journeys replace subsystem-led commands. |
| Correctness and data integrity | 2 | 4 | Typed contracts, atomic state, and contract fixtures close known gaps. |
| Architectural coherence | 2 | 5 | A pure core and thin adapters establish one dependency direction. |
| Maintainability | 2 | 5 | One orchestration service replaces repeated workflow assembly. |
| Testability | 3 | 5 | Contract, migration, and security fixtures test behavior at boundaries. |
| Security and privacy | 2 | 5 | Explicit execution policy and safe artifact boundaries become defaults. |
| CLI UX and accessibility | 2 | 5 | Clear outcomes, progressive help, and plain-text-first rendering reduce cognitive load. |
| Performance | 3 | 4 | Shared exclusions and bounded reads prevent pathological scans. |
| Operability | 2 | 5 | Reproducible toolchain, observable outcomes, and durable run state improve diagnosis. |
| Developer experience | 2 | 5 | Narrow typed APIs and stable fixtures make changes easier to reason about. |

## Chosen direction

Use a parallel typed v2 core behind adapters, then migrate vertical workflows
one at a time. This is safer than a clean rewrite because the existing artifact,
MCP, and compatibility contracts carry user value; it is more coherent than
continuing in-place patches because the current orchestration boundary is the
source of much of the complexity. See [TARGET.md](TARGET.md) and
[EXEC_PLAN.md](EXEC_PLAN.md) for the system definition and milestones.
