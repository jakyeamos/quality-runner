# Changelog

All notable changes to Quality Runner are documented here.

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
