# Modernization Progress

## Current state

M0 is implemented on the protected branch `codex/gpt56-modernization`, based
on `main` commit `0a3def1`. The branch remains isolated until review and merge.

M0 restores the public trust boundary without changing artifact schema ids:

- package metadata now derives from `quality_runner/_version.py`; the plugin,
  wheel, CLI, MCP, and release-tag contracts are checked together;
- artifact, compatibility-certifier, explicit export, and rollout-output paths
  reject unsafe segments and symlinked ancestors or leaves;
- discovered gates are evidence-only by default; explicit execution requires a
  disposable checkout and is documented as arbitrary local code, not a sandbox;
- Fresh Review reports `packet-ready` or incomplete outcomes truthfully instead
  of resembling a completed no-findings review.

## Decisions in force

- Use a parallel typed core with controlled adapters, not a clean rewrite.
- Treat the CLI/MCP workflow as the primary interface; do not build a web UI as
  part of this modernization.
- Preserve public artifact and compatibility contracts while making execution
  safer by default.
- Keep `CITATION.cff` on the last published release until the tagged release
  commit updates it; the tag workflow verifies that parity explicitly.

## Baseline quality

- Full tests, Ruff lint/format, Vulture, a fresh package build, and
  `quality-runner release-smoke --json` pass.
- Basedpyright still reports 14 pre-existing errors concentrated in the Fresh
  Review typed-dictionary boundary; M1 owns that typed-contract migration.

## Next milestone

M1 establishes typed v2 contracts and the migration harness. It must preserve
the hardened M0 behavior while eliminating the remaining Fresh Review type
boundary debt.
