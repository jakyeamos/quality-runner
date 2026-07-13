# Quality Runner

Quality Runner is a local-first audit-and-plan quality orchestrator for code
repositories.

It inspects a target repo, compiles standards, detects available quality gates,
normalizes evidence-backed findings, writes `.quality-runner/` artifacts, and
produces an ordered remediation plan. It does not edit source files, install
dependencies, create commits, call remote services, or execute remediation.

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

From PyPI:

```bash
uv tool install quality-runner
```

Package page: [quality-runner on PyPI](https://pypi.org/project/quality-runner/).

To install directly from the public repository instead:

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

Quality Runner also carries compatibility surfaces for the two smaller extracted
packages it supersedes publicly:

- `quality_evidence_contract` imports remain available for shared evidence and
  finding schema normalization.
- `repo-quality-certifier`, `repo-quality-certifier-mcp`, and
  `repo_quality_certifier` remain available for existing gate-certification
  callers while new work should lead with `quality-runner`.

## Quickstart

Start with the outcome-first journeys. Each result names the state, the strength
of the evidence, what was written, the safety mode, and one next action.

```bash
quality-runner audit /path/to/repo --run-id baseline-001 --json
quality-runner review /path/to/repo --mode blind --json
quality-runner verify /path/to/repo --run-id baseline-001-verify --json
quality-runner runs /path/to/repo --json
```

`audit` creates evidence and a remediation plan without editing source files.
`review` makes a prepared packet visibly `awaiting-evidence`, rather than
treating the absence of a packet-bound local response as clean. `verify`
records discovered gates by default; `runs` reads history without adding a
summary file. All four journeys emit the v2 outcome by default.
Fresh Review is deliberately two-phase: prepare a packet first, then submit a
response that is bound to that packet. The [CLI Reference](docs/cli.md#quality-runner-review)
explains the boundary and handoff model.

To authorize discovered commands after reviewing their evidence, use a disposable
checkout explicitly:

```bash
quality-runner verify /path/to/repo \
  --execute-gates --worktree-mode disposable --json
```

Disposable execution protects the ordinary source checkout from normal gate
mutations; it is not a sandbox for arbitrary commands. See the
[CLI Reference](docs/cli.md) for the full execution and dirty-worktree contract.

Legacy `inspect`, `run`, `verify-gates`, `status`, and orchestration commands
remain available for compatibility. Use `refresh` when a controller needs its
established combined v1 workflow and handoff export:

```bash
quality-runner refresh /path/to/repo \
  --run-id-prefix baseline-001 \
  --handoff-output /path/to/repo/.quality-runner/exports/baseline-001-handoff.md \
  --json
```

The [Upgrade and Compatibility Guide](docs/upgrade.md) defines the v2 command
mappings, v1 support window, and non-destructive rollback procedure. Use
`review --legacy-output` only when an existing CLI consumer requires v1 JSON.

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
  slice-specs/
    remediate-<slice-id>.md
  agent-handoff.json
  agent-handoff.md
```

The normal workflow is:

1. Read `agent-handoff.md`.
2. Read the queued slice spec under `slice-specs/` when one exists.
3. Review `quality-audit.json` for evidence-backed findings.
4. Review `code-quality-scan.json` for structural warnings and line evidence.
5. Review `remediation-plan.json` for ordered actions and verification gates.
6. For multi-slice work, convert the QR handoff into GSD-style phases, plans,
   ledgers, and batch summaries before editing.
7. Execute one coherent batch at a time.
8. Rerun Quality Runner to confirm findings clear and update the resolution ledger.

See [Agent Usage](docs/agent-usage.md) for the copy-paste phase and batch
templates agents should follow.

## Commands

For new work, begin with the four outcome-first commands:

```bash
quality-runner audit /path/to/repo --json
quality-runner review /path/to/repo --mode blind --json
quality-runner verify /path/to/repo --json
quality-runner runs /path/to/repo --json
```

Their JSON payload uses `quality-runner-outcome-v0.2`; the detailed definitions
and safety behavior live in the [CLI Reference](docs/cli.md). The established
commands below remain callable as supported v1 compatibility paths; see the
[Upgrade and Compatibility Guide](docs/upgrade.md) before migrating automation.

```bash
quality-runner doctor
quality-runner init /path/to/repo --json
quality-runner status /path/to/repo --json
quality-runner inspect /path/to/repo --json
quality-runner run /path/to/repo --json
quality-runner verify-gates /path/to/repo --json
quality-runner refresh /path/to/repo --run-id-prefix refresh-001 --handoff-output handoff.md --json
quality-runner refresh /path/to/repo --run-id-prefix task-001-pass-1 \
  --intent "Implement the requested task" --review-cycle-id task-001 \
  --review-iteration 1 --json
quality-runner release-smoke --json
quality-runner validate-report worker-report.json --json
quality-runner validate-handoff handoff.json --json
quality-runner validate-slice-spec slice-spec.md --json
quality-runner review-worker /path/to/repo --baseline-run-id before --final-run-id after --worker-report worker-report.json --json
quality-runner controller-report lint worker-report.json --strict --json
quality-runner export-handoff /path/to/repo
quality-runner export-slice-specs /path/to/repo --run-id run-001 --json
quality-runner-mcp
repo-quality-certifier plan --repo-root /path/to/repo --json
repo-quality-certifier-mcp
```

`inspect` and `run` scan the currently checked-out branch by default. If that
branch is neither `main` nor the local branch with the highest commit count,
`repo-scan.json` includes a warning. Use
`--checkout-most-advanced-branch` to switch to that local most-advanced branch
before scanning; the worktree must be clean.

See [CLI Reference](docs/cli.md) for command details.

`refresh` runs inspect, run, verify, and summarize. Its default verification is
evidence-only: command-backed gates are reported as
`execution-consent-required` until explicit disposable execution is authorized.
`gates-clean` therefore means explicitly run local gates passed, while
`gates-blocked` and `gates-failed` distinguish missing consent or environment
constraints from executed command failures. Blocked or failed handoffs include `blocker_groups` and
`next_slice.action_groups` for structured routing. Use `--handoff-output` when
you want the scan and the human remediation plan from one command; use
`export-handoff` later to regenerate or copy a handoff from an existing run.
`export-slice-specs` regenerates per-slice cold-executor plans under
`slice-specs/`. For large remediations, agents should use QR output as evidence
for a GSD-style phase plan rather than editing directly from the handoff. For a
single queued slice, start from the matching `slice-specs/<slice-id>.md` when
present.

For an agent-driven implement-review loop, pass the task through the existing
`--intent` or `--intent-file` input and add `--review-cycle-id` plus a
1-based `--review-iteration`. Quality Runner writes `review-delta.json` and
`review-delta.md` after each refresh. The agent applies task-scoped fixes and
calls `refresh` again with the previous verify run as `--baseline-run-id` until
the delta recommends `stop`. Quality Runner remains read-only; unrelated
findings are retained as `out_of_scope` without blocking the task.

Before release, run `quality-runner release-smoke --json` to verify the public
doctor contract, v2 audit outcome, handoff export, report compatibility, and
the packaged `quality_evidence_contract` / `repo_quality_certifier` surfaces.

## MCP

New MCP integrations should use the additive outcome tools:

- `quality_runner_audit_outcome`
- `quality_runner_review_outcome`
- `quality_runner_verify_outcome`
- `quality_runner_runs_outcome`

They retain the standard MCP wrapper while exposing the v2 outcome as
`structuredContent`. The established v1 MCP tools remain available for existing
clients; use `tools/list` as the authoritative current tool/schema registry.

For compatibility with prior Repo Quality Certifier consumers, the
`repo-quality-certifier-mcp` command remains packaged and exposes:

- `repo_quality_certifier_plan`
- `repo_quality_certifier_doc_quality`

See [MCP Integration](docs/mcp.md) for JSON-RPC examples and tool payloads.

## Artifacts

Quality Runner writes versioned JSON and Markdown artifacts. See
[Artifact Contract](docs/artifacts.md) for the current v1 artifact set and
field-level guarantees. Treat generated target-repository evidence as
potentially sensitive until it has been reviewed for local paths, gate output,
and source-derived content.

Semantic code similarity is a structural quality signal, not an automatic
refactor. When `similarity-ts`, `similarity-py`, or `similarity-rs` are already
installed locally, QR runs them read-only and normalizes high-confidence matches
into `code-quality-scan.json` deduplicate findings and `SIM-###` clusters. QR
does not install these tools. Disable or tune similarity under
`[quality_runner.structural_scan]` (for example `similarity_enabled = false` or
`disabled_rule_groups = ["deduplicate"]`).

## DOI-Ready Research Release

Quality Runner is prepared as an independent software-methods artifact. See
[RESEARCH_READY.md](RESEARCH_READY.md) and
[docs/release-notes/v0.3.1-doi.md](docs/release-notes/v0.3.1-doi.md) for the
citable artifact boundary, validation path, data-availability policy, and claim
limits.

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
repo-policy reference. For opt-in layer-boundary rules, see
[Architecture Contracts](docs/architecture-contracts.md). For opt-in user-defined
standards packs, see [Quality Skills](docs/quality-skills.md).

## Scan Exclusions

Discovery skips fixture corpora, docs, vendored trees, generated corpora, and
tool output directories by default so embedded samples are not reported as
product workspaces. Add repo-specific exclusions in `.quality-runner.toml`:

```toml
[quality_runner]
scan_exclusions = ["samples", "generated-reports/**"]
```

## Safety Boundary

Quality Runner may create or update files under
`.quality-runner/runs/<run-id>/` in the target repository. It does not edit
source files, install dependencies, create commits, call remote services, or
execute remediation. Discovered gate commands are evidence-only unless the
caller explicitly requests disposable execution.

Every generated remediation slice includes verification guidance, but a separate
coding agent must receive user approval before implementation.

## Development

Run the full local ladder:

```bash
uv sync --locked --all-groups
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked basedpyright
uv run --locked vulture quality_runner quality_evidence_contract repo_quality_certifier tests scripts --min-confidence 70
uv run --locked python scripts/run_pytest_with_lcov.py
uv run --locked quality-runner release-smoke --json
pre-cr run --workspace . --json  # changed-line readiness; expects changed files
```

See [Troubleshooting](docs/troubleshooting.md) for common install and runtime
issues.

See [Release Checklist](docs/release.md) for PyPI and Homebrew packaging notes,
and the [Upgrade and Compatibility Guide](docs/upgrade.md) for cutover and
rollback behavior.
