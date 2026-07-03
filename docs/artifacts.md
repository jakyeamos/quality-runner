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
  instruction files, language-aware quality commands, mature repo surfaces,
  nested workspaces, active scan exclusions, ecosystems, generated-code markers,
  local CI checks, Pre-CR config, project truth file presence, and branch
  selection warnings when the checked-out branch is neither `main` nor the local
  most-advanced branch.
- `code-quality-scan.json`: deterministic structural/code-quality findings,
  line accountability, duplicate clusters, skipped generated/vendor paths, and
  non-blocking remediation buckets.
- `package-manager-preflight.json`: detected package-manager state, declared
  `packageManager`, lockfiles, and non-blocking warnings such as mixed lockfiles.
- `standards.json`: compiled standards packet for the selected profile,
  including saved custom profile settings when a repo-defined profile is used.
- `capability-matrix.json`: available and missing repo-owned quality gates.
  Available command-backed capabilities include the command, source, detected
  language, optional owner/severity policy, required-by provenance, and local CI
  status evidence. `verification_state` separates discovery evidence from
  command execution evidence and pass/fail evidence. CI-only gates that have no
  local executor are marked with `local_execution: "ci-only"`. Capabilities also
  include `capability_kind` so local commands, CI-only gates, and file/evidence
  capabilities can be handled independently.
- `run-manifest.json`: run metadata, Quality Runner version, artifact paths, and
  git HEAD/branch/dirty state when the target is a git repo.

## Run Artifacts

`quality-runner run` writes all inspect artifacts plus:

- `quality-audit.json`: evidence-backed findings with severity, optional owner,
  category, evidence, recommended fix, verification, and optional aggregate
  score for grouped structural findings.
- `remediation-plan.json`: adoption stage, stopping criteria, and ordered
  remediation slices with priority, actions, findings, and verification gates.
- `resolution-ledger.json`: current finding lifecycle state by stable
  fingerprint, preserving accepted dispositions and marking disappeared
  findings fixed on later runs.
- `resolution-ledger.md`: human-readable resolution ledger summary.
- `agent-handoff.json`: machine-readable next-slice handoff, including adoption
  stage, stopping criteria, missing repo-owned gates with suggested commands,
  gate verification status/classification for verified runs, gate blockers with
  setup guidance, primary blocker class, grouped blocker routing, and
  runner-provided structural checks that produced findings.
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
- `agent-handoff.json`
- `agent-handoff.md`
- `run-manifest.json`

When `read_only_gates` is active, QR snapshots the tracked git diff before each
executed local command. If a safe-looking command mutates tracked files, QR
restores the pre-gate tracked diff, marks the gate with
`failure_type=read-only-mutation`, and classifies the run as a
`read-only-gate-blocker`.

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

Artifact schema ids stay on `v0.1` while changes are additive and old consumers
can continue to read previous fields unchanged. New optional fields may appear
in artifacts and schemas, but existing required fields keep their meaning.

A schema id must move to the next minor version before a release that removes a
field, changes a field meaning, changes a required field type, or makes an
optional field required.

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
