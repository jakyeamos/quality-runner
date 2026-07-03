# Changelog

All notable changes to Quality Runner are documented here.

## 0.2.1 - 2026-07-02

- Clarified handoff output by separating missing repo-owned quality gates from
  runner-provided structural checks.
- Added explicit `gates-blocked` and `gates-failed` handoff statuses with
  gate-verification classification, blocker summaries, and dependency setup
  commands in `agent-handoff.json` and `agent-handoff.md`.
- Added read-only gate mutation detection for tracked files, including
  pre-gate diff restoration and `read-only-mutation` gate diagnostics.
- Added primary blocker class and blocker groups to gate handoffs so mixed
  blocker runs can route dependency setup, read-only policy, environment, and
  command failures separately.
- Added structured gate-blocker `action_groups` on blocked/failed handoff
  next slices and deduplicated repeated dependency setup commands across gates.
- Added an Action Groups section to `agent-handoff.md` so human readers see the
  same blocker-class grouping and deduped actions that controllers read from
  `agent-handoff.json`.
- Improved pnpm non-interactive dependency restoration guidance so
  `ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY` points workers at one interactive
  `pnpm install --frozen-lockfile` setup step before rerunning QR gates.
- Added suggested commands for missing repo-owned gates in `agent-handoff.json`
  and `agent-handoff.md`.
- Added ignored-path scan previews, interactive one-run inclusion prompts, and
  `.quality-runner.toml` `structural_scan.include_ignored_paths` support.
- Expanded structural scanning with API boundary, UI structural, bundle-budget,
  and Ponytail-debt rules.
- Added aggregate structural scores to audit findings so remediation slices are
  ordered by impact within each priority tier.
- Added branch-selection warnings for repo scans and
  `--checkout-most-advanced-branch` for explicitly scanning the local branch
  with the highest commit count.

## 0.2.0 - 2026-07-02

- Added the default-on structural/code-quality scan and `code-quality-scan.json`
  artifact with ranked findings, stable fingerprints, line accountability,
  duplicate clusters, skipped/generated file evidence, and remediation buckets.
- Added `resolution-ledger.json` and `resolution-ledger.md` as the resolution ledger
  for current and prior structural finding dispositions, including unresolved, fixed,
  accepted-intentional, accepted-false-positive, and blocked-with-prerequisite.
- Updated remediation planning and agent handoff output so structural findings
  are grouped remediation work instead of one slice per line while capability
  gaps remain blocker-capable.
- Added `.quality-runner.toml` structural scan controls for disabled rule groups,
  threshold overrides, and accepted dispositions with owner/reason metadata.
- Completed the scanner module split so Quality Runner's own default structural
  scan no longer reports large-source-file findings for the scanner internals.
- Renamed the built-in standards profile to `default` and simplified CLI/MCP
  examples so profile overrides are optional.
- Added repository-local custom standards profiles under
  `.quality-runner.toml`.

## 0.1.0 - 2026-06-28

- Added standalone audit-and-plan workflow.
- Added `.quality-runner/runs/<run-id>/` artifact writer with path and symlink
  hardening.
- Added repository discovery, standards compilation, capability detection, audit
  findings, remediation planning, and agent handoff generation.
- Added CLI commands: `doctor`, `init`, `status`, `inspect`, `run`, and
  `export-handoff`.
- Added MCP tools: `quality_runner_doctor`, `quality_runner_inspect_repo`,
  `quality_runner_run`, `quality_runner_status`, and
  `quality_runner_export_handoff`.
- Added `.quality-runner.toml` config loading, accepted exceptions, packaged
  JSON schemas, run manifests, git metadata capture, and a dogfood fixture
  corpus.
- Added plugin metadata and skill documentation.
- Added package build/install smoke tests and global-tool install support.
