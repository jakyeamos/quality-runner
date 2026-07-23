# Quality Runner Project Truth

Last updated: 2026-07-22

## Current State

Quality Runner is a public, local-first quality orchestration package. It
inspects repositories, records evidence, plans remediation, and hands execution
to separately authorized humans or agents. It does not own autonomous source
changes or remote review execution.

`main` is the published 0.6.0 release at `c6e92cc`, tagged `v0.6.0`, with
successful post-merge CI run 32, a successful tag workflow run 13, and a
verified PyPI distribution. The public
wheel digest is `34c96cedfbe555033cfbde863e4144c13fd91510d512f1b482428d5181a3c1d9`
and the source archive digest is
`99445e86ea7fe686380f3e291d67ffbf20420f500fe6b3fb9562b5d72bdf277e`. A fresh
PyPI install passes version, doctor, release-smoke, and MCP discovery. The
protected `codex/gpt56-modernization` branch contains the typed v2 trust-boundary,
Fresh Review, audit, verification, and journey work through `8705cc1`; M7
redaction and release hardening complete in `279cc8a`. `c71b130` adds the
pinned dependency audit and untrusted baseline validation. `b193900` adds the
release-profile readiness contract, and `67bd698` completes the remaining
quality workflow port. The architecture-preserving port is integrated and
published on canonical `dev` as v0.6.0; its evidence remains attached to the
port commits and release promotion.

The short `qr` console command is part of the canonical dev CLI surface and
the published 0.6.0 package. The reviewed `codex/dev-fold-qr-adaptive-timeouts`
integration at `49c3dda` folds local timeout calibration without changing the
published release surface. The scoped `codex/qr-flexible-scan-scope` follow-up
at `4b0c2ab` makes scan scope agent-selectable and keeps protected runtime and
artifact paths fail-closed. Commit `0de7d75` adds fail-closed `--only-gate`
selection and carries selected gate IDs through verification, outcomes, and
workflow preflight. Its 73 focused tests, Ruff, Basedpyright, changed-file
formatting, Vulture, release-smoke, source build, and installed-wheel smoke
pass. The full suite recorded 738 passes and one network-blocked packaged
console-script test; that exact test passed under the approved network path.
No tag, registry, or published artifact changed.

The follow-up agent-instruction audit at `3952a54` aligns the detailed guide
and packaged skill with current `qr` journeys, v2 outcomes, scan-scope,
review/gate/planning/worker/rollout/release routes, and cache provenance. The
environment-legibility candidate at `e1a56da` is activated in the existing
`developer-experience` pack at version `0.1.1`; the personal corpus remains
active with the manifest and active-pack list unchanged.

## Current Position

- Target: a typed v2 core behind CLI, MCP, and compatibility adapters.
- Reviewed integration: `a66850d` combines the adaptive timeout and incremental
  analysis/artifact folds and is ready as the promoted `dev` tip.
- Active follow-up: `codex/qr-flexible-scan-scope` at `0de7d75`; no merge,
  publish, tag, or registry change has occurred.
- `codex/release-0.6.0` was merged by PR #5 into `main` at `c6e92cc`; `main`
  and the `v0.6.0` tag are published.
- `dev` is the canonical integration branch, is published to `origin/dev`, and
  the reviewed combined fold is `a66850d`.
  The temporary `codex/dev-feature-port` worktree/ref and the superseded
  `quality-skill-corpus-workflow` branch were pruned after the behavioral port
  audit; unrelated active branches remain separate.
- Canonical planning documents: `docs/modernization/`.
- Combined fold verification: 133 focused tests, Ruff, formatting, Basedpyright,
  Vulture, source-size, and diff checks pass; the full suite has 687 behavioral
  passes and one network-blocked packaged-build check.
- Scan-scope follow-up verification: 92 focused tests, Ruff, Basedpyright,
  compileall, scoped Vulture, and diff checks pass; 732 behavioral tests pass
  with only the unavailable-`uv` packaging test deselected.
- Environment-legibility activation verification: candidate ingest and
  classification return no errors; the active `developer-experience` pack is
  version `0.1.1` with exactly two namespaced environment-legibility entries.
- Selected-gate verification: 73 focused tests, Ruff, Basedpyright,
  changed-file formatting, Vulture, release-smoke, source build, and isolated
  wheel smoke pass; the full-suite packaging failure was reproduced as a
  network-only issue and passed when rerun with network access.
- Agent-instruction audit: live `git ls-remote --heads origin` confirms the
  remote branch set is `main` at `9f6c677`, `dev` at `ca2e34b`, and the current
  follow-up at `0159b3a`. The older local `codex/ci-warning-cleanup` and
  `codex/qr-command-surface` refs are not additional current remote branches.
- Public compatibility: retain `quality_evidence_contract` and
  `repo_quality_certifier` during a published transition window.

## Core Contract

- Local-first operation with no silent remote transfer.
- Auditing/planning stays separate from source mutation.
- JSON artifacts remain canonical; Markdown remains the human decision surface.
- Scan-only and code-executing verification are explicit, separately reported
  modes.
- Primary CLI journeys are outcome-first; legacy JSON is an explicit supported
  compatibility projection rather than a silent default.

## Baseline Quality

- `c6e92cc` is the released v0.6.0 promotion commit. GitHub PR-head CI and
  the tag release workflow pass; the public PyPI wheel and source archive are
  verified by digest, and an isolated PyPI install passes CLI, doctor,
  release-smoke, and MCP checks.
- `49c3dda` integrates `0bc7d37`, which adds candidate/active local timeout
  baselines, exclusion-bound identity validation, phase budgets, explicit
  overrides, and 86 focused regression tests; Ruff, formatting, Basedpyright,
  Vulture, and the full suite's 666 behavioral tests pass. The packaged build
  check needs network access to resolve uncached uv dependencies.
- `a66850d` combines that timeout fold with the incremental analysis, semantic
  reuse, exclusion-estimation, and verification-deadline work; 133 focused
  tests and all static gates pass, while the full suite has 687 behavioral
  passes and the packaged build remains network-blocked.
- `c71b130` passes the full 556-test pytest suite, Ruff lint/format,
  Basedpyright, Vulture, lock validation, pip-audit, release smoke, build, and
  installed-wheel smoke checks. GitHub CI and the tag release workflow pass;
  the published PyPI wheel passes an independent disposable-install smoke.
- Basedpyright reports zero errors; audit, review, verify, and run history now
  have a versioned v2 outcome contract behind preserved v1 projections.
- Release smoke now checks package/runtime/plugin parity and the release
  workflow enforces tag, wheel, manifest, citation, and MCP outcome contracts.
- `da79745` ports the first Quality Skills contract batch into the v0.5.1
  application architecture: deterministic coverage, review verification
  contracts, redacted finding metadata, skill identities, and manifest/schema
  support. The touched-module slice passes 63 tests, Ruff, formatting,
  compilation, and Basedpyright.
- `94b2d42` ports canonical global skill-corpus selection, repository signal
  scoring, QR-native similarity, module-status reporting, and workflow/run
  summary exposure while retaining the v0.5.1 application seams. The focused
  port slice passes 78 tests, Ruff, formatting, compilation, and Basedpyright.
- `f75c431` adds repository-configured artifact redaction and retention,
  redacts append-only gate responses at write time, and exposes a
  dry-run-by-default `prune-artifacts` command while retaining symlink-safe
  artifact path handling. The focused artifact/CLI slice passes 77 tests,
  Ruff, formatting, and Basedpyright.
- `f292a1e` adds the source-first consumer runner surface: a checkout-aware
  Python command builder, an executable latest/local launcher, and rollout
  provenance/rerun commands that identify the QR source and version. The
  focused rollout/tooling slice passes 9 tests plus launcher smoke checks.
- `831d9a4` exposes corpus classification, append, and synchronization through
  the skill CLI, keeping sync dry-run by default and validating review reports
  against the selected local/global skill set. The focused skill/corpus/CLI
  slice passes 62 tests, Ruff, formatting, and BasedPyright.
- `87d81f8` adds the tool-neutral `remediation-delta` comparison and CLI
  surface, persisting current/baseline evidence without modifying GSD or QR
  planning files. The focused remediation/delta/CLI slice passes 52 tests,
  Ruff, formatting, and BasedPyright.
- `960d094` adds QR-owned native phase planning: security-first domain
  candidates, deterministic waves and dependencies, batch summaries, delta
  updates, verification/close state, and a complete CLI/schema contract while
  preserving the root GSD planning namespace. The focused phase/config/delta/
  CLI slice passes 60 tests, Ruff, formatting, and BasedPyright.
- `74e368a` ports scan-exclusion preflight with deterministic candidate packets,
  review/validate/apply staging, protected-path and symlink checks, module-
  scoped exclusion overlays, security-coverage preservation, CLI/artifact/
  manifest wiring, and persistent config support. The full 604-test suite,
  Ruff, formatting, and BasedPyright pass.
- `287fe95` adds the source-read-only remediation-context contract: bounded
  slice context records, risk-aware evidence requirements, plan/handoff
  readiness references, `remediation-context.json` artifact wiring for run and
  verify workflows, and the `validate-remediation-context` CLI. The full
  609-test suite, Ruff, formatting, and BasedPyright pass.
- `546122e` keeps the remediation-delta module under QR's default 500-line
  source threshold without changing its evidence contract; the focused delta
  and source-size checks pass.
- `67bd698` completes the remaining source-branch quality surfaces while
  retaining the current application and compatibility architecture; the full
  650-test suite, Ruff, formatting, BasedPyright, and release smoke pass.

`b5a610e` keeps exact CI workflow commands during release-gate discovery;
  focused regression tests pass, exact-head GitHub CI is green, and the release
  profile passes on the promoted release candidate.

- `5217270` passes the full 669-test suite, Ruff lint/format, Basedpyright,
  Vulture, and the source-size guard; no QR gate was invoked.

## Risks

- Generated evidence can contain target-repository output; it remains local and
  must be handled as potentially sensitive even after source-evidence redaction.
- Existing large-file warnings remain in `repo_quality_certifier/core.py` and
  `tests/test_cli.py`.
- User-authored gate commands remain arbitrary code; M0 requires explicit
  consent and a disposable checkout but does not sandbox those commands.
- Combined file-adapter task provenance remains the baseline-compatible string
  `"None"` until a published compatibility cutover can change that projection.
- Persistent scan exclusions require review evidence and explicit `--apply`;
  run-only overlays are intentionally recorded as non-mutating evidence.
- Fresh remediation contexts intentionally begin as `needs-understanding` and
  block handoff validation until the external worker records the required
  evidence for its selected slice.
- The release profile intentionally blocks without current CI provenance,
  repo-local release evidence, disposable execution where required, and owner
  acceptance; it does not infer release readiness from configured commands.
- Refresh timeout baselines remain local under `.quality-runner/cache` and are
  invalidated by repository-surface, exclusion, policy, version, or gate-plan
  changes; they are not release evidence.
- `fa291c2` passes 41 focused cache/exclusion/artifact tests, 103 broader
  code-quality/security/config/artifact tests, Ruff, BasedPyright, and Vulture;
  Quality Runner gate execution was not invoked.
- The normal commit hook for `5217270` completed successfully in 301 seconds;
  it retained the existing `tests/test_cli.py` oversized-source warning.
- The `a66850d` integration commit's 90-second Pre-CR guard timed out and
  recorded the existing weak-test and oversized-test warnings; no bypass flag
  was used.

## Recent Progress
- 2026-07-22: `0de7d75` adds fail-closed `--only-gate` selection and carries
  selected gate IDs through verification, outcomes, and workflow preflight;
  focused/static/package checks pass and the branch remains unmerged.
- 2026-07-21: `3952a54` aligns the detailed agent guide and packaged skill
  with current `qr` journeys, v2 outcomes, scan-scope controls, review/gate/
  planning/worker/rollout/release routes, and cache provenance; six focused
  documentation tests pass. The subsequent live origin refresh confirms the
  pushed branch alongside `dev` and `main`.
- 2026-07-22: `e1a56da` adds the environment-legibility candidate and isolates
  global Git configuration in tests; explicit activation then updated the
  active `developer-experience` pack to `0.1.1` without changing the manifest.
- 2026-07-21: `4b0c2ab` adds explicit bounded and full-scan inclusion
  controls, protected-path fail-closed behavior, inclusion provenance, and
  refresh/verify propagation; 732 behavioral tests pass.
- 2026-07-19: `a66850d` combines the adaptive-timeout and incremental-artifact
  folds; 133 focused tests and static checks pass, with 687 full-suite
  behavioral passes and one network-blocked packaged-build check.
- 2026-07-18: `dbb892f` preserves verification deadlines through Git discovery
  and keeps timeout artifacts attributable to the verification mode.
- 2026-07-18: `f99fec1` completes read-only verify-gates analysis reuse and
  execution-consent-safe fallback behavior; Tenure dogfood completed without
  timeout or gate execution, with all 11 discovered gates skipped.
- 2026-07-18: `5217270` completes refresh cache wiring, semantic cache reuse,
  cache evidence, and warm-prefix regression coverage; 669 tests passed.
- 2026-07-18: `fa291c2` integrates the local P1 excluded-artifact estimate fix
  with safe incremental scan caching and refresh artifact retention in an
  isolated revision; no push, publish, release, or gate execution occurred.
- 2026-07-18: `81d560d` makes read-only planning cache-free, records disabled
  cache evidence, and verifies the full relevant suite without gate execution.
- 2026-07-17: `4d7f72b` stops recursive estimates for protected/generated/
  excluded artifact directories, adds 10,000-file inspect/preflight regression
  coverage, and distinguishes actual scan work in timeout diagnostics.
- 2026-07-17: `b5a610e` makes release-gate discovery execute the exact commands
  declared by CI, including scoped Vulture coverage; focused tests pass and
  exact-head GitHub CI is green.
- 2026-07-17: `a3777b1` fixes release-profile discovery for dynamic package
  versions and installed-wheel release smoke, with 49 focused tests passing.
- 2026-07-17: PR #5 merged the validated v0.6.0 branch at `c6e92cc`; tag
  `v0.6.0` and release workflow run 13 succeeded, PyPI 0.6.0 is published,
  and a fresh public-install smoke passed.
- 2026-07-17: Folded the short `qr` console command into the canonical `dev`
  line from `codex/qr-command-surface-main`; focused entrypoint tests, Ruff,
  formatting, and diff checks pass. No version bump or release tag was made.
