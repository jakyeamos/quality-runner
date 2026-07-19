# Quality Runner Project Truth

Last updated: 2026-07-19

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
protected
`codex/gpt56-modernization` branch contains M0 trust-boundary work in
`f36dcf4`, M1 typed Fresh Review contracts in `cb12746`, M2 typed read-only
audit orchestration in `3f23204`, and M3 typed verification orchestration in
`8705cc1`. M4 in `75d8ac4` adds the additive v2 journey-outcome contract,
outcome-first CLI/MCP surfaces, bounded run history, and precise safety
projections. M5 in `f5c8610` completes the two-phase Fresh Review lifecycle:
strict packet-bound local responses, isolated combined packets, auditable
handoffs, and truthful artifact/outcome reporting. The modernization branch
has been merged and published. M6 began in
`0b5ac2e`: application-owned audit, verification, and journey services now sit
behind explicit workflow and outcome façades, with installed-wheel facade
checks. M6 completes in `56c94d4`: packet construction and report normalization
now have application owners, while root review façades retain their v1 type and
direct-combined compatibility contracts. M7 is complete: `113f143` redacts
secret-like candidate literals before they are fingerprinted or persisted, and
`66ce3ef` locks the development toolchain while testing doctor, v2 outcomes,
and MCP discovery from the built wheel. `32e7b26` makes CLI Fresh Review v2
outcome-first, with an explicit stderr-noticed v1 projection through 0.7.x;
the MCP v1 tool remains a separate compatibility surface. `633b96e` records
candidate-aware upgrade, rollback, release, and sensitive-artifact guidance.
`dc09ec0` proves that a default v2 Review run still persists v1-readable
context, manifest, and report artifacts. `9fcea7d` restores legacy positional
workflow slots, freezes the published v1 Review field shape, and re-exports the
public `ReviewFinding` type while retaining explicit v2 next-action guidance.
`4dee5af` shares redaction across security candidates, code-quality findings,
and remediation excerpts so source-secret markers do not persist in those paths;
`27deaa4` moves the helper to a neutral module to preserve the import boundary.
`cd30948` requires release tags to be ancestors of `main`, smoke-tests default
v2 and frozen v1 Review behavior from installed wheels, and corrects the
release, rollback, and Homebrew guidance. M7 completes in `279cc8a`: source
evidence redaction now covers multiline typed, concatenated, and template
literals across code-quality, remediation excerpts, and security candidates;
CI/release and installed-wheel tests execute the MCP v2 Review outcome.
Independent post-M7 review found four P2 release blockers. `bf6c9e7` closes
the source-evidence redaction bypasses for typed, commented, and expression
assignments. `b4b5e6e` preserves the v0.1 gate schema, emits the consent-aware
v0.2 artifact, and repairs the packaged skill and clean-install release path.
`141635e` completes the focused source-evidence hardening with lexical context
for private fields, malformed syntax, computed logging, and tokenless values.
`948107f` prepares the v0.5.1 citation, changelog, upgrade guidance, and public
README. `c71b130` adds a pinned Python dependency audit and validates untrusted
baseline Git revisions before review-delta comparisons. Its reviewed merge,
tag, release workflow, and published-artifact smoke checks have completed.
`b193900` adds the release-profile readiness contract: repository and CI
provenance, repo-local release evidence validation, aggregate command coverage,
artifact-manifest/read-only gates, publication-boundary review triggers, CLI and
refresh evidence overrides, and compatibility-preserving v0.5.1 wiring.
`67bd698` completes the remaining quality workflow port: local-first self-update,
stderr progress reporting, resolution-aware planning, domain phase candidates,
read-only filesystem integrity, structured verification contracts, skill
decomposition, UI quality fixtures, and starter-pack examples.
The architecture-preserving port is now integrated and published on canonical
`dev` as v0.6.0; its 650-test/static-analysis/release-smoke evidence remains
attached to the port commits and the release promotion.
The short `qr` console command is now part of the canonical dev CLI surface. It
maps to the same `quality_runner.cli:main` entrypoint as `quality-runner`, is
included in the v0.6.0 package, and is covered by packaged entrypoint tests.
The isolated `codex/release-0.6.0` branch completed at `e3f5f5f`; PR #5 merged
it into `main` at `c6e92cc`. The release-readiness contract recognizes dynamic
`_version.py` metadata and the installed-wheel `release-smoke` CI command.
Workflow discovery keeps the exact commands declared by CI, with 49 focused
regression tests, green exact-head GitHub CI, a passing release profile, and
verified PyPI publication.

The isolated `codex/qr-adaptive-timeouts` follow-up at `0bc7d37` adds local,
identity-bound refresh timeout calibration without changing the published
release surface.

## Current Position

- Target: a typed v2 core behind CLI, MCP, and compatibility adapters.
- Next slice: start the next scoped follow-up from the released `main`/`dev`
  baseline.
- `codex/release-0.6.0` was merged by PR #5 into `main` at `c6e92cc`; `main`
  and the `v0.6.0` tag are published.
- `dev` is the canonical integration branch, is published to `origin/dev`, and
  is synchronized to `c6e92cc`.
  The temporary `codex/dev-feature-port` worktree/ref and the superseded
  `quality-skill-corpus-workflow` branch were pruned after the behavioral port
  audit; unrelated active branches remain separate.
- Canonical planning documents: `docs/modernization/`.
- `codex/qr-adaptive-timeouts` implements repo-calibrated refresh budgets; it
  remains isolated and unpublished pending review.
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
- `0bc7d37` adds candidate/active local timeout baselines, exclusion-bound
  identity validation, phase budgets, explicit overrides, and 86 focused
  regression tests; Ruff, formatting, Basedpyright, Vulture, and the full
  suite's 666 behavioral tests pass. The packaged build check needs network
  access to resolve uncached uv dependencies.
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

## Recent Progress

- 2026-07-19: `0bc7d37` adds repo-calibrated refresh timeout baselines with
  three-run activation, exclusion preflight binding, phase/total budgets, and
  explicit timeout provenance; focused tests and static checks pass.
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
- 2026-07-17: `67bd698` completes the remaining quality workflow port with
  local self-update, progress, resolution-aware planning, phase candidates,
  read-only integrity, verification contracts, skill decomposition, UI quality,
  starter packs, and 650 passing tests.
- 2026-07-17: canonical `dev` receives the architecture-preserving port and is
  published to `origin/dev`; the completed port branch and superseded source
  branch are pruned, while unrelated active branches remain untouched.
- 2026-07-17: `b193900` ports release-profile readiness with provenance,
  repo-local evidence validation, aggregate coverage, artifact/read-only gates,
  publication review triggers, CLI/refresh propagation, and 621 passing tests.
- 2026-07-17: `287fe95` adds remediation-context packets and readiness
  validation to run/verify artifacts while keeping source changes external and
  preserving the v0.5.1 application/compatibility seams.
- 2026-07-17: `74e368a` adds scan-exclusion preflight and module-aware run-only
  overlays while preserving security coverage for structural/code-quality
  exclusions and retaining the current application/compatibility façades.
- 2026-07-17: `546122e` reduces remediation-delta implementation noise while
  preserving its fingerprints, package evidence, and recommendation payload.
- 2026-07-17: `960d094` adds the native QR phase lifecycle and domain-aware
  `plan auto` workflow under `.planning/quality-runner/`; it remains advisory,
  idempotent, and separate from source changes, commits, pushes, and root GSD.
- 2026-07-17: `87d81f8` adds remediation delta evidence and the explicit
  `remediation-delta` command, preserving the boundary between QR evidence and
  project planning systems.
- 2026-07-17: `831d9a4` completes the skill corpus command surface for
  classify/append/sync and makes selected-skill review coverage explicit.
