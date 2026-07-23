# Quality Runner agent router

Read this router first, then use [the context index](.agents/context/README.md)
to load only the packet that matches the task.

## Invariants

- Quality Runner is local-first: audit and planning may read target repositories,
  but must not edit, merge, push, deploy, publish, or contact a remote service
  without explicit approval.
- Preserve target checkout state, generated artifacts, caches, and unrelated
  work. Use a disposable copy for any command that needs mutation.
- Treat JSON artifacts and provenance as canonical. Never invent evidence from
  documentation alone; distinguish absent, stale, blocked, and verified.
- Do not load or transmit credentials, prompts, transcripts, private diffs, or
  whole repositories. Redact sensitive evidence before persistence.
- Release, schema, compatibility, CI, registry, and publication changes need
  explicit approval and review. No history rewrites or verification bypasses.

## Routing

- Architecture or ownership: `architecture.md`.
- Commands, gates, or setup: `commands.md`.
- Python style or compatibility: `conventions.md`.
- Secrets, artifacts, or network behavior: `security.md`.
- A failed or stale run: `failure-modes.md`.
- A design or implementation example: `examples.md`.
- Completion or review criteria: `done.md`.
- Release, publication, or rollback: `deployment.md`.

The live project snapshot is [PROJECT_TRUTH.md](.tracker/PROJECT_TRUTH.md).
