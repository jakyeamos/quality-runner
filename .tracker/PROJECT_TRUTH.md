# Quality Runner Project Truth

Last updated: 2026-07-04

Quality Runner is the public, installable quality orchestration package. It owns
the CLI/MCP workflow for repo inspection, gate evidence, audit generation,
remediation planning, handoff export, and controller report validation.

Quality Runner now also has DOI-ready software-methods metadata and release
docs: `CITATION.cff`, `.zenodo.json`, `RESEARCH_READY.md`, and
`docs/release-notes/v0.3.1-doi.md`.

Version `0.3.1` is the compatibility release candidate for replacing direct
`quality-evidence-contract` and `repo-quality-certifier` consumers with the
single Quality Runner package.

The package also carries compatibility surfaces for earlier extracted quality
packages when those APIs are still imported by active tools:

- `quality_evidence_contract` remains available for shared evidence and finding
  schema normalization.
- `repo_quality_certifier`, `repo-quality-certifier`, and
  `repo-quality-certifier-mcp` remain available as compatibility surfaces for
  older gate-certification callers.

New public positioning and new integrations should lead with `quality-runner`.

The README install section now points directly to the live PyPI package page and
keeps the repository install path as the alternate source-checkout route.

Current package-mining state:

- The `quality-runner` wheel includes `quality_evidence_contract`,
  `repo_quality_certifier`, both repo-quality-certifier console scripts, and
  the certifier plugin manifest/skill package data.
- `quality-runner release-smoke` now verifies compatibility imports,
  repo-quality-certifier artifact generation, certifier MCP tool metadata, and
  packaged plugin manifests.
- Release docs target `v0.3.1` and include post-install checks for the
  compatibility imports, CLI, MCP, and release smoke before archiving old repos.
- `quality-runner rollout` is the first-class multi-repo controller workflow
  for safe sequential refreshes, repo-list parsing, per-repo controller reports,
  validation artifacts, rollout ledgers, per-repo planning summaries, and
  fleet remediation phase drafts for all-projects stress passes.
- AIOS now exposes `aios quality rollout` as a thin launch-and-capture adapter
  over this workflow; Quality Runner still owns the controller protocol and
  artifact contract.

Current verification:

- 2026-07-04: Documented the AIOS launch shortcut in the rollout controller
  notes. Verified with `uv run pytest -q tests/test_rollout.py
  tests/test_release_docs.py` and `uv run ruff check docs/qr-rollout-20260702.md`
  (Ruff reported no Python files under the Markdown path and exited cleanly).
- 2026-07-04: Added DOI-ready software-methods metadata and release notes.
  Verified the passing DOI path with `uv run ruff check quality_runner tests`,
  `uv run pytest -q`, and `uv run quality-runner release-smoke --json`.
  DOI minting is still blocked by existing format drift in five files and
  existing basedpyright debt in tests.
- 2026-07-04: QR now excludes generated artifact surfaces from both recursive
  discovery and structural source scanning: build/test outputs, local caches,
  top-level artifact output dirs, lockfiles/build metadata, and
  `generated-*` source artifacts. Verified with regression tests, full
  `uv run ruff check .`, `uv run basedpyright`, full `uv run pytest -q`, and a
  non-mutating BBDSE `BBDS-Analytics-Product-Suite` smoke where discovery took
  0.544s and code-quality scanning took 6.437s.
- 2026-07-04: `quality-runner rollout` now writes fleet planning documents by
  default: `per-repo-summaries/INDEX.md`, one per-repo summary document per
  rollout entry, and `fleet-remediation-phases.md`. Verified with focused
  rollout tests, focused ruff on rollout/document files, `uv run basedpyright`,
  and full `uv run pytest -q`. Full `uv run ruff check .` is currently blocked
  by a pre-existing dirty scan-exclusion import-order issue outside this
  rollout-document change.
- 2026-07-04: Branch-scan warnings now compare commit identity, so a checked
  out `dev` branch aligned to `main` does not emit
  `checked_out_branch_not_main_or_most_advanced`. Verified with the focused
  branch workflow tests, a full `uv run pytest -q`, and a real QR run against
  `agent-eval-contract` that returned no warnings.
- 2026-07-04: `uv run ruff check .`, `uv run basedpyright`, and
  `uv run pytest` passed after the README install documentation update.

## QR Remediation Planning

- 2026-07-04: Added GSD Phase 1 for QR remediation from qr-fleet-continue-20260704-quality-runner; 1 plan(s) created from quality-runner.md. Execution has not started.
