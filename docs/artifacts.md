# Artifact Contract

Artifacts are written under:

```text
<repo>/.quality-runner/runs/<run-id>/
```

`run-id` must be a single path segment. Absolute paths, separators, `.` and
`..` are rejected.

## Inspect Artifacts

`quality-runner inspect` writes:

- `repo-scan.json`: repository facts such as package scripts, lockfiles, agent
  instruction files, discovered intent docs (`PRODUCT.md`, `DESIGN.md`,
  `CONTEXT.md`, `docs/adr/*.md`), language-aware quality commands, mature repo
  surfaces, nested workspaces, active scan exclusions, ecosystems,
  generated-code markers, local CI checks, Pre-CR config, project truth file
  presence, and branch selection warnings when the checked-out branch is neither
  `main` nor the local most-advanced branch.
- `code-quality-scan.json`: deterministic structural/code-quality findings,
  line accountability, duplicate clusters, skipped generated/vendor paths, and
  non-blocking remediation buckets. When locally installed `similarity-ts`,
  `similarity-py`, or `similarity-rs` binaries are available, QR also records
  semantic similarity clusters (`SIM-###`) alongside regex-based duplicate
  clusters (`DUP-###`). QR never installs these tools; missing binaries are
  recorded as non-blocking skipped scanner status. Opt-in architecture-contract findings use
  category `architecture` when configured in `.quality-runner.toml`. Opt-in
  Quality Skill findings use category `skill:<skill-id>` when configured.
  Partially built or unwired work uses category `integrate`; see
  [Unwired Work Detection](unwired-work.md).
- `package-manager-preflight.json`: detected package-manager state, declared
  `packageManager`, lockfiles, and non-blocking warnings such as mixed lockfiles.
- `standards.json`: compiled standards packet for the selected profile,
  including saved custom profile settings when a repo-defined profile is used.
  `sources` includes profile/config paths, agent instruction files, truth file,
  and discovered intent docs as `intent:<type>` entries.
- `capability-matrix.json`: available and missing repo-owned quality gates.
  Available command-backed capabilities include the command, source, detected
  language, optional owner/severity policy, required-by provenance, and local CI
  status evidence. `verification_state` separates discovery evidence from
  command execution evidence and pass/fail evidence. CI-only gates that have no
  local executor are marked with `local_execution: "ci-only"`. Capabilities also
  include `capability_kind` so local commands, CI-only gates, and file/evidence
  capabilities can be handled independently.
- `run-manifest.json`: run metadata, Quality Runner version, artifact paths, and
  git HEAD/branch/dirty state when the target is a git repo. When author intent
  is supplied, the manifest also embeds the resolved `intent` packet.

## Author Intent

`inspect`, `run`, `verify-gates`, and `refresh` accept optional author intent
through `--intent` or `--intent-file`. Intent captures what the user set out to
accomplish, not a description of the diff.

When present, QR writes:

- `intent.json`: schema `quality-runner-intent-v0.1` with `goal`, optional
  `constraints`, `non_goals`, `tradeoffs`, `risk_areas`, and
  `verification_expectations`, plus provenance fields (`source`, `supplied_by`,
  `captured_at`).
- embedded `intent` on `run-manifest.json`, `agent-handoff.json`, and
  `run-summary.json` when those artifacts are produced.

The Markdown handoff renders intent under an `## Intent` section so human agents
see the same goal context as controllers reading JSON. When `repo-scan.json`
includes `intent_docs`, the handoff also lists relevant repo intent documents
under `## Relevant Repo Intent Docs` so workers read ADRs and product/design
context before editing. QR surfaces these paths only; it does not semantically
interpret long-form intent documents.

`--intent-file` must point at JSON inside the target repository. The file must
include a non-empty `goal` string; other intent fields are optional lists or
strings.

## Gate Controller Artifacts

QR Gate is an optional controller protocol layered on top of existing run
artifacts. It stays source-read-only: `gate-respond` appends decision history
only and never edits repository source files.

`quality-runner gate` reads an existing run (typically a verify or refresh run)
and writes:

```text
<repo>/.quality-runner/gate-runs/<gate-run-id>/
  gate-run.json
  gate-responses.jsonl
  intent.json            # only when --intent/--intent-file is supplied and the source run has no intent
```

`gate-run.json` uses schema `quality-runner-gate-run-v0.1` and records:

- linked `run_id`
- `status`: `awaiting-response`, `ready-to-proceed`, `completed`, or `aborted`
- `phase`: `post-run` or `post-verify`
- `lifecycle_status` and optional `awaiting` routing (`blocker-routing`,
  `finding-triage`, `author-decision`, `workflow-timeout`)
- artifact paths back to the source run handoff, audit, and gate verification

`gate-responses.jsonl` is append-only. Each line uses schema
`quality-runner-gate-response-v0.1` with `action` in
`approve|fix|skip|route-next-slice|record-disposition|abort`, optional
`finding_ids`, and provenance (`actor`, `at`, `notes`). `record-disposition`
also records `disposition`, `owner`, resolved `fingerprints`, and updates the
source run's `resolution-ledger.json` `finding_dispositions` when present.

## Fix Proposal Artifacts

`quality-runner propose-fix` writes `fix-proposals.json` for a remediation
finding group without editing repository source files. The artifact uses schema
`quality-runner-fix-proposals-v0.1` and always records `implementation_allowed:
false` and `applied: false`.

Each proposal links to a finding id (and optional fingerprint) from the selected
remediation slice or handoff `next_slice`. Proposal kinds are:

- `instruction` — recommended fix plus verification steps for mechanical findings
- `command` — explicit setup or gate command for blocker-class findings
- `unified-diff` — reserved for future unified diff payloads; QR core does not
  apply patches

Every proposal and the parent artifact include deterministic `checksum`
fields so external executors can detect tampering. QR never applies proposals;
an external agent or human applies changes and reruns Quality Runner.

## Run Artifacts

`quality-runner run` writes all inspect artifacts plus:

- `quality-audit.json`: evidence-backed findings with severity, optional owner,
  category, evidence, recommended fix, verification, optional aggregate
  score for grouped structural findings, optional finding-quality metadata
  (`impact`, `effort`, `fix_risk`, `confidence`, `why_now`, `leverage`), and
  deterministic `actionability` routing (`fix-now`, `triage`, `accept-risk`,
  `defer`, `informational`) with `actionability_rationale`.
- `remediation-plan.json`: adoption stage, stopping criteria, and ordered
  remediation slices with priority, actions, findings, and verification gates.
  Each slice may also include executor-facing metadata:
  - `impact`, `effort`, `fix_risk`, `confidence`, `why_now`
  - `leverage` with deterministic `rank` used for ordering after severity
  - `planned_at` (`head`, `branch`, `dirty`) captured from run-manifest git state
  - `drift_check` with a `git diff --stat <sha>..HEAD -- <paths>` command over
    in-scope paths
  - `scope` with `in_scope` and `out_of_scope` boundaries
  - `stop_conditions` for when workers should stop and report instead of editing
  - per-finding `evidence_excerpt` with line context for structural rows
  Structural scan slices are advisory clusters by file so an external agent can
  choose one coherent batch without Quality Runner executing remediation.
  `integrate` findings produce decision slices that ask whether to wire, finish,
  descope, or accept WIP rather than defaulting to cleanup.
- `resolution-ledger.json`: current finding lifecycle state by stable
  fingerprint, preserving accepted dispositions and marking disappeared
  findings as superseded by the current scan unless an external actor records a
  more specific disposition. Optional `finding_dispositions` records audit
  finding ids accepted through `gate-respond record-disposition` and links
  back to gate-run history.
- `resolution-ledger.md`: human-readable resolution ledger summary.
- `security-scan.json`: opt-in security capability discovery, candidate
  findings, and agent-review gate metadata when
  `[quality_runner.security]` is configured.
- `slice-specs/`: per-slice Markdown cold-executor plans derived from QR
  evidence. One file per remediation slice:
  `slice-specs/<slice-id>.md`. Each spec is self-contained and includes:
  - why this matters
  - current state with evidence excerpts
  - commands needed and per-step verification
  - in-scope and out-of-scope boundaries
  - ordered steps and done criteria
  - STOP conditions
  - planned-at git state and drift-check command when available
  - leverage summary and relevant repo intent docs
  - maintenance notes reminding workers that QR does not apply fixes
  Use `quality-runner export-slice-specs` to regenerate specs for an existing
  run. Use `quality-runner validate-slice-spec` to lint a generated file. See
  [`docs/examples/slice-spec-structural-harden.md`](examples/slice-spec-structural-harden.md)
  for a representative structural slice spec.
- `agent-handoff.json`: machine-readable next-slice handoff using schema
  `quality-runner-agent-handoff-v0.2`, including adoption
  stage, stopping criteria, optional embedded `intent`, optional `intent_docs`,
  `lifecycle_status`
  (`audit-clean`, `gates-clean`, `merge-ready`, `blocked`, `failed`,
  `workflow-timeout`, `needs-triage`), missing repo-owned gates with suggested
  commands, gate verification status/classification for verified runs, gate
  blockers with setup guidance, primary blocker class, grouped blocker routing,
  and runner-provided structural checks that produced findings.
  `merge-ready` means local gates passed and every ingested CI check reports
  `conclusion: success`; it is separate from handoff `status` values such as
  `gates-clean`.
- `agent-handoff.md`: human-readable handoff for a coding agent. The Markdown
  intentionally separates missing repo-owned gates such as `pnpm test` or
  `pnpm typecheck` from Quality Runner's built-in structural checks so readers
  do not mistake a runner heuristic for a repo-native test, build, or typecheck
  gate. For blocked or failed verification runs, it puts gate blockers before
  structural remediation and uses `gates-blocked` or `gates-failed` status so
  controllers can route the next slice to dependency setup, environment
  remediation, or failing executable gates first. It also names the
  staged-adoption stopping point so a mature repo can add gates, scope scans,
  classify debt, or fix high-signal findings without treating one-pass QR clean
  as the only successful outcome.

## Gate Verification Artifacts

`quality-runner verify-gates` executes discovered command-backed capabilities,
skips CI-only capabilities that have no local executor, skips non-executable
file/evidence capabilities without blocking, and writes:

- `repo-scan.json`
- `code-quality-scan.json`
- `package-manager-preflight.json`
- `standards.json`
- `capability-matrix.json`: updated so locally executed gates have
  `verification_state.execution = "local-executed"` and result `passed` or
  `failed`.
- `gate-verification.json`: per-gate command, source, exit code, duration,
  timeout, capability kind, bounded stdout/stderr tail fields, skipped reason,
  failure type, recommended environment action, and status.
- `quality-audit.json`
- `remediation-plan.json`
- `slice-specs/`
- `agent-handoff.json`
- `agent-handoff.md`
- `run-manifest.json`

When `read_only_gates` is active, QR snapshots the tracked git diff before each
executed local command. If a safe-looking command mutates tracked files, QR
restores the pre-gate tracked diff, marks the gate with
`failure_type=read-only-mutation`, and classifies the run as a
`read-only-gate-blocker`.

`verify-gates` and `refresh` accept `--worktree-mode in-place|disposable`.
Disposable mode creates a detached git worktree at the current `HEAD` under
`.quality-runner/worktrees/<run-id>/`, executes gates inside that isolated copy,
writes QR artifacts to the original repository, and removes the worktree when
verification completes. Gate results record `verification_context` on
`gate-verification.json` with `worktree_mode`, `base_head`, `execution_root`,
`mutations_isolated`, and optional `dirty_source_worktree`.

Disposable mode refuses a dirty source worktree unless
`--allow-dirty-worktree-verify` is set. In disposable mode, mutating gates may
run inside the isolated worktree even when `read_only_gates` is active, because
the user's working tree is not mutated.

This command is intentionally separate from `inspect` and `run` so capability
discovery, command execution, and command pass/fail are distinguishable. For
JavaScript package scripts, the executable command runs through the detected
package manager, for example `pnpm run lint`, so local `node_modules/.bin`
resolution matches normal developer usage.

Aggregate gates such as `pre_cr` and `pre_pr` are skipped when already-covered
leaf gates have passed, which avoids rerunning the same formatter, lint,
typecheck, test, build, dead-code, or smoke commands in one verification pass.
Environment-sensitive failures such as localhost bind denials, pipe permission
errors, and sandbox-like permission failures are classified as blocked
environment restrictions rather than ordinary repo gate failures.

Dependency setup failures are also classified separately from ordinary command
failures. When a package manager reports non-interactive dependency
restoration, the failed gate includes `diagnostics.dependency_setup` with the
package manager, gate cwd, recommended setup command, and cause. Later gates
that share the same package-manager/cwd context are skipped with
`skip_type: "dependency-setup-blocked"` and `blocked_by` pointing at the first
failed gate, so one missing install does not produce repeated noisy failures.
For pnpm ignored build-script approval failures, the setup command points to
`pnpm approve-builds`. For pnpm no-TTY module replacement failures, the setup
guidance points at one interactive `pnpm install --frozen-lockfile` run before
rerunning QR gates.

Blocked and failed gate handoffs include `primary_blocker_class`,
`blocker_groups`, and next-slice `action_groups`. The flat `actions` list stays
present for backward-compatible human reading, while `action_groups` gives
controllers structured blocker-class routing and deduplicates repeated setup
commands across gates that share the same dependency setup blocker. The
Markdown handoff renders these groups under the next slice's `Action Groups`
section so human workers see the same grouping without inspecting JSON.

## Handoff Quality Lint

`quality-runner validate-handoff` checks schema validity plus executor-readiness
rules that JSON Schema alone does not capture:

- every slice has at least one machine-checkable verification command
- every slice has STOP conditions
- every slice has `planned_at` git state when the target repo is a git checkout
- structural slices anchor to file/line/fingerprint evidence
- handoff keeps `implementation_allowed=false`

`quality-runner validate-slice-spec` applies the same content bar to generated
Markdown under `slice-specs/`.

## Worker Review Artifacts

`quality-runner review-worker` does not write repo artifacts. It returns JSON
schema `quality-runner-review-worker-result-v0.1` comparing:

- baseline vs final `code-quality-scan.json` fingerprint deltas
- final handoff status and lifecycle classification
- worker report validity and scope compliance warnings

Use it after a worker claims completion and before a controller merges or
advances the next slice.

## Safety Guarantees

Quality Runner rejects:

- unsafe run ids
- symlinked `.quality-runner`, `runs`, or run-directory components before writes
- symlinked artifact leaf files before writes
- symlinked handoff export paths before reads

By default, Quality Runner v1 does not edit files outside its artifact
directory. `inspect` and `run` can explicitly switch branches first with
`--checkout-most-advanced-branch`; that mode requires a clean git worktree.

## Compatibility Policy

Most artifact schema ids stay on `v0.1` while changes are additive and old
consumers can continue to read previous fields unchanged. New optional fields
may appear in artifacts and schemas, but existing required fields keep their
meaning.

A schema id must move to the next minor version before a release that removes a
field, changes a field meaning, changes a required field type, or makes an
optional field required.

`agent-handoff.json` moved to `quality-runner-agent-handoff-v0.2` because the
controller-facing routing contract expanded from a generic planned/executed
handoff into explicit `gates-blocked`, `gates-failed`, and `gates-clean`
statuses plus structured `gate_verification.blocker_groups` and
`next_slice.action_groups`. The new fields are still optional for consumers
that only read the flat `actions` list, but controllers should key new routing
logic off the `v0.2` schema id.

## Local CI Status

`quality-runner inspect` and `quality-runner run` accept
`--ci-status-json <path>` for a local export shaped as:

```json
{
  "checks": [
    {
      "name": "Quality / Lint",
      "status": "completed",
      "conclusion": "success",
      "url": "https://example.invalid/check"
    }
  ]
}
```

The file must live inside the target repo and is read as evidence only. Quality
Runner does not call GitHub, fetch live check runs, or execute commands from CI
configuration.

## Scan Exclusions

Discovery skips common non-product trees by default: `docs`, `fixtures`,
`corpus`, `generated-corpus`, `generated-corpora`, `vendor`, `vendors`,
`vendored`, and `third_party`, alongside tool output directories such as
`.git`, `.quality-runner`, `node_modules`, `dist`, and `build`.

Root `.gitignore` entries are also applied during traversal, so untracked
ignored dependency, cache, generated, or nested-project directories are pruned
before recursive descent.

Repos can add more patterns in `.quality-runner.toml`:

```toml
[quality_runner]
scan_exclusions = ["samples", "generated-reports/**"]
```

The active list is written to `repo-scan.json` as `scan_exclusions`.
