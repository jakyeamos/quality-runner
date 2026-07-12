# Modernization Progress

## Current state

M0 and M1 are implemented on the protected branch
`codex/gpt56-modernization`, based on `main` commit `0a3def1`. The branch
remains isolated until review and merge.

M0 restores the public trust boundary without changing artifact schema ids:

- package metadata now derives from `quality_runner/_version.py`; the plugin,
  wheel, CLI, MCP, and release-tag contracts are checked together;
- artifact, compatibility-certifier, explicit export, and rollout-output paths
  reject unsafe segments and symlinked ancestors or leaves;
- discovered gates are evidence-only by default; explicit execution requires a
  disposable checkout and is documented as arbitrary local code, not a sandbox;
- Fresh Review reports `packet-ready` or incomplete outcomes truthfully instead
  of resembling a completed no-findings review.

M1 establishes the typed migration seam without changing the v1 Fresh Review
projections:

- strict normalized packet, report, manifest, adapter, and known-issue records
  now live in `quality_runner.core`; application serializers own the v1
  projection boundary;
- public `review_types` and `review_context` retain their permissive v1 typed
  dictionary contracts, including direct combined packet callers;
- task, blind, combined, and direct-combined packet projections have committed
  M0 baseline fixtures, while v1 readers enforce their published closed-object
  schema boundaries;
- CLI and MCP review paths build strict internal values before persisting the
  identical v1 JSON artifacts.

## Decisions in force

- Use a parallel typed core with controlled adapters, not a clean rewrite.
- Treat the CLI/MCP workflow as the primary interface; do not build a web UI as
  part of this modernization.
- Preserve public artifact and compatibility contracts while making execution
  safer by default.
- Keep `CITATION.cff` on the last published release until the tagged release
  commit updates it; the tag workflow verifies that parity explicitly.
- Treat v1 payloads and Python typed dictionaries as compatibility projections;
  strict core contracts must not leak into legacy entrypoint annotations.

## Quality status

- `pytest` passes 436 tests; Basedpyright reports zero errors.
- Ruff lint/format, Vulture, a fresh package build, and
  `quality-runner release-smoke --json` pass.

## Next milestone

M2 migrates the read-only audit vertical slice through one typed application
use case while preserving inspect/run artifacts, finding IDs, CLI/MCP output,
and handoff expectations.
