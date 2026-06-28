# Changelog

All notable changes to Quality Runner are documented here.

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
