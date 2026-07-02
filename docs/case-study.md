# Backend Platform Case Study

Quality Runner is a local-first audit-and-plan platform for agentic development
workflows. It does not attempt to fix code directly. Instead, it produces
versioned evidence artifacts that make repository quality state explicit before
a human or coding agent chooses a remediation slice.

## Problem

Modern coding agents can run tests, read docs, and make edits quickly, but they
often lack a stable contract for deciding whether a repository is ready for the
next change. Quality Runner addresses that gap by turning repository facts into
structured artifacts:

- what languages and quality commands exist
- which standards profile applies
- which gates are available or missing
- which structural/code-quality warnings are present
- what evidence supports each audit finding
- which remediation slice should be handed to an implementation agent next

## Architecture

The backend pipeline is intentionally boring and inspectable:

1. `discovery` reads repository facts, language signals, package scripts,
   Python project metadata, recursive workspace manifests, mature-codebase
   surfaces, CI workflow command evidence, Pre-CR config, and truth-file
   presence while applying scan exclusions.
2. `standards` compiles the selected profile and local config into a standards
   packet.
3. `capabilities` maps discovered evidence to required quality gates.
4. `code_quality` adds deterministic structural scan evidence, duplicate
   clusters, file accountability, and finding lifecycle data.
5. `audit` converts missing or conflicting evidence into normalized findings.
6. `planning` groups capability gaps and structural findings into remediation
   buckets and an agent handoff.
7. `workflow` writes the complete `.quality-runner/runs/<run-id>/` artifact set.

This keeps each stage testable without hiding policy decisions inside CLI code.

## Safety Boundary

Quality Runner v1 is audit-and-plan only. It may write under
`.quality-runner/runs/<run-id>/` in the target repository. It must not edit source
files, install dependencies, create commits, call remote services, or execute
remediation.

Artifact writing is guarded against unsafe run IDs and symlink escapes. The run
manifest captures git state so handoffs can be tied back to a concrete checkout.

## Showpiece Fix

The original self-audit exposed a platform-quality issue: Quality Runner passed
its real Python ladder, but its own audit reported missing formatter, lint,
typecheck, tests, build, dead-code, smoke, pre-PR, and truth-file gates because
capability detection only trusted JavaScript package scripts.

The release-ready version adds language-aware command evidence:

- Python gates from `pyproject.toml`
- nested workspace gates from child `package.json`, `pyproject.toml`,
  `Cargo.toml`, and `go.mod` manifests
- default scan exclusions for fixture corpora, docs, vendored examples, and
  generated corpora
- CI command evidence from GitHub workflow text
- Pre-CR `testCommand` evidence from `.pre-cr.json`
- JavaScript package-script evidence preserved for JS repositories
- truth-file required only when present, configured, or demanded by local policy

The result is a more credible backend platform: findings now reflect actual repo
evidence rather than assumptions about one ecosystem.

The 0.2.0 release-prep pass adds a second showpiece: Quality Runner now produces
`code-quality-scan.json`, `resolution-ledger.json`, and `resolution-ledger.md`
by default, then splits its own scanner internals so a self-audit does not need
accepted dispositions for large-source-file warnings.

## Release Evidence

Local verification for the release-ready branch includes:

- `python3.14 -m pytest -q`
- `ruff check .`
- `ruff format --check .`
- `basedpyright`
- `vulture . --min-confidence 70`
- `uv run --with pytest pytest -q`
- `python3.14 scripts/run_pytest_with_lcov.py`
- `uv build`
- `pre-cr run --workspace . --json`
- installed wheel smoke checks for `quality-runner`, `quality-runner doctor`, and
  `quality-runner-mcp`
- `quality-runner run . --run-id pre-release-self-audit --json`
  with no capability blockers and no default structural findings

PyPI and Homebrew publishing remain external release steps: PyPI Trusted
Publisher must be configured before tagging `v0.2.0`, and the Homebrew formula
can only be finalized after the real PyPI source distribution and SHA-256 exist.

## Why It Is Hiring-Manager Ready

This project demonstrates backend-platform fundamentals: explicit artifact
contracts, language-aware discovery, typed Python modules, CLI and MCP surfaces,
security-conscious file writes, behavior-focused tests, CI/release workflows,
and a clear separation between audit decisions and implementation side effects.
