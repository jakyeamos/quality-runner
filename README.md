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

After the first PyPI release:

```bash
uv tool install quality-runner
```

Install from the repository while the package is pre-release:

```bash
uv tool install git+ssh://git@github.com/jakyeamos/quality-runner.git
```

For local development:

```bash
git clone git@github.com:jakyeamos/quality-runner.git
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
quality-runner export-handoff /path/to/repo
quality-runner-mcp
```

See [CLI Reference](docs/cli.md) for command details.

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

The built-in profile is `default`. See
[Standards Profiles](docs/standards-profiles.md) for the current behavior and
the planned profile-extension boundary.

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
