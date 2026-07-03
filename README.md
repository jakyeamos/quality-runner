# Quality Runner

Quality Runner is a local-first audit-and-plan quality orchestrator for code
repositories.

It inspects a target repo, compiles standards, detects available quality gates,
normalizes evidence-backed findings, writes `.quality-runner/` artifacts, and
produces an ordered remediation plan. Version 1 does not edit source files,
install dependencies, create commits, call remote services, or execute
remediation.

## Why this exists

Agentic coding workflows need a reliable way to separate evidence from opinion.
Quality Runner turns repository facts, local standards, and available quality
gates into versioned artifacts that another agent or human maintainer can review
before approving implementation work.

## Architecture

The pipeline is intentionally small: repository discovery compiles facts and
quality-command evidence, standards compilation applies a profile, capability
detection identifies available and missing gates, audit generation normalizes
findings, and remediation planning writes an agent handoff.

See [Backend Platform Case Study](docs/case-study.md) for the design narrative,
self-audit improvements, and release-readiness proof.

## Install

From PyPI after the package has been published:

```bash
uv tool install quality-runner
```

Until then, install from the public repository:

```bash
uv tool install git+https://github.com/jakyeamos/quality-runner.git
```

For local development:

```bash
git clone https://github.com/jakyeamos/quality-runner.git
cd quality-runner
uv tool install --editable . --force
```

Verify the installed commands:

```bash
quality-runner --version
quality-runner-mcp --version
quality-runner doctor --json
```

## Quickstart

Run a full audit-and-plan pass against a repository:

```bash
quality-runner run /path/to/repo --run-id baseline-001 --json
```

Quality Runner writes artifacts under the target repo:

```text
/path/to/repo/.quality-runner/runs/baseline-001/
  repo-scan.json
  code-quality-scan.json
  package-manager-preflight.json
  standards.json
  capability-matrix.json
  run-manifest.json
  quality-audit.json
  remediation-plan.json
  resolution-ledger.json
  resolution-ledger.md
  agent-handoff.json
  agent-handoff.md
```

The normal workflow is:

1. Read `agent-handoff.md`.
2. Review `quality-audit.json` for evidence-backed findings.
3. Review `code-quality-scan.json` for structural warnings and line evidence.
4. Review `remediation-plan.json` for ordered actions and verification gates.
5. Give an approved remediation slice to a coding agent.
6. Rerun Quality Runner to confirm findings clear and update the resolution ledger.

## Commands

```bash
quality-runner doctor
quality-runner init /path/to/repo --json
quality-runner status /path/to/repo --json
quality-runner inspect /path/to/repo --json
quality-runner run /path/to/repo --json
quality-runner verify-gates /path/to/repo --json
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --json
quality-runner validate-report worker-report.json --json
quality-runner export-handoff /path/to/repo
quality-runner-mcp
```

`inspect` and `run` scan the currently checked-out branch by default. If that
branch is neither `main` nor the local branch with the highest commit count,
`repo-scan.json` includes a warning. Use
`--checkout-most-advanced-branch` to switch to that local most-advanced branch
before scanning; the worktree must be clean.

See [CLI Reference](docs/cli.md) for command details.

`refresh` runs inspect, run, verify, and summarize in read-only mode. Its
handoff statuses are intended for controllers: `gates-clean` means discovered
local gates passed, `gates-blocked` means environment/dependency/read-only
policy blocked evidence, and `gates-failed` means executable repo gates ran and
failed. Blocked or failed handoffs include `blocker_groups` and
`next_slice.action_groups` for structured routing.

## MCP

The MCP server exposes:

- `quality_runner_doctor`
- `quality_runner_inspect_repo`
- `quality_runner_run`
- `quality_runner_status`
- `quality_runner_export_handoff`

See [MCP Integration](docs/mcp.md) for JSON-RPC examples and tool payloads.

## Artifacts

Quality Runner writes versioned JSON and Markdown artifacts. See
[Artifact Contract](docs/artifacts.md) for the current v1 artifact set and
field-level guarantees.

## Standards Profiles

The built-in profile is `default`. Repos can also save custom profiles in
`.quality-runner.toml`:

```bash
quality-runner init /path/to/repo --json
```

```toml
[quality_runner]
default_profile = "team"

[quality_runner.profiles.team]
extends = "default"
required_capabilities = ["lint", "typecheck", "tests", "dead_code"]
allowed_package_managers = ["pnpm", "bun"]
```

After saving the config, the custom profile is selected automatically by
`default_profile`, or explicitly with:

```bash
quality-runner run /path/to/repo --profile team --json
```

See [Standards Profiles](docs/standards-profiles.md) for the full profile and
repo-policy reference.

## Scan Exclusions

Discovery skips fixture corpora, docs, vendored trees, generated corpora, and
tool output directories by default so embedded samples are not reported as
product workspaces. Add repo-specific exclusions in `.quality-runner.toml`:

```toml
[quality_runner]
scan_exclusions = ["samples", "generated-reports/**"]
```

## v1 Safety Boundary

Quality Runner v1 may create or update files under `.quality-runner/runs/<run-id>/`
in the target repository. It must not edit source files, install dependencies,
create commits, call remote services, or execute remediation.

Every generated remediation slice includes verification guidance, but a separate
coding agent must receive user approval before implementation.

## Development

Run the full local ladder:

```bash
python3.14 -m pytest -q
ruff check .
ruff format --check .
basedpyright
vulture . --min-confidence 70
uv run --with pytest pytest -q
python3.14 scripts/run_pytest_with_lcov.py
pre-cr run --workspace . --json  # changed-line readiness; expects changed files
```

See [Troubleshooting](docs/troubleshooting.md) for common install and runtime
issues.

See [Release Checklist](docs/release.md) for PyPI and Homebrew packaging notes.
