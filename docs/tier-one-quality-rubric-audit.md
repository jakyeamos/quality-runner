# Tier 1 Quality Rubric Audit

Date: 2026-07-01

## Scope

This audit applies a Tier 1 rubric to Quality Runner itself. Tier 1 means the
project is safe and dependable enough for local developer use, but not yet
treated as a mature multi-profile quality platform.

TMCP was used for routing, source harvesting, and evidence discipline. The
harvest produced thin domain signals rather than a complete domain playbook, so
the rubric substance is derived from repository evidence: README contracts,
artifact docs, standards-profile docs, CI/release workflows, source code, tests,
Quality Runner self-audit artifacts, and local quality-gate results.

## Rubric

Each dimension is scored from 0 to 4.

| Dimension | Weight | Tier 1 bar |
| --- | ---: | --- |
| Safety boundary | 4 | The tool is audit-and-plan only, writes only declared artifacts, and does not edit source, install dependencies, commit, call remote services, or execute remediation. |
| Artifact contract | 4 | Public JSON and Markdown artifacts are versioned, documented, schema-backed, and protected against path traversal or symlink escapes. |
| Audit fidelity | 5 | Findings reflect the target repo's actual language, commands, CI, and documented quality contract instead of assuming one ecosystem. |
| Quality gate coverage | 4 | Format, lint, typecheck, tests, dead-code, build, smoke, and release checks are runnable and represented in CI or documented local workflow. |
| Test value | 4 | Tests protect CLI, MCP, workflow, artifact, config, discovery, and safety contracts with behavior-level assertions. |
| Release readiness | 3 | Build, wheel install, console-script smoke checks, release workflow, and publishing handoff are documented and current. |
| Developer experience | 3 | Setup, command reference, troubleshooting, and handoff docs let a new maintainer run and interpret the tool without hidden context. |

Weighted score: 85 / 108, or 79%.

Tier result: conditional pass for Tier 1. The implementation and package checks
are strong, but audit fidelity and Pre-CR integration need remediation before
the project should be treated as a trusted general-purpose quality runner.

Post-remediation note: the release-ready showpiece pass added language-aware
quality command evidence, corrected truth-file semantics, documented Pre-CR as
changed-line readiness, and raised executable-line LCOV to 92.4%. A self-audit
run on 2026-07-01 returned `clean`.

2026-07-02 release-prep update: the 0.2.0 branch adds the structural/code-quality
scan, resolution ledger, grouped structural remediation, accepted dispositions,
and scanner module split. The remaining release blocker is external: PyPI
Trusted Publisher must be configured before tagging `v0.2.0`; the Homebrew
formula should be updated only after the published PyPI source distribution
exists.

## Audit Findings

### P1: Self-audit misclassifies this Python repo's gates as missing

Quality Runner passes the real Python ladder, but `quality-runner run .` returns
`planned` with blocker findings for formatter, lint, typecheck, tests,
dead-code, and truth file. The generated `repo-scan.json` identifies the repo as
Python but records no scripts and no package manager. The generated
`capability-matrix.json` then reports only `pre_cr` as available.

Evidence:

- `quality_runner/discovery.py` reads command scripts only from `package.json`.
- `quality_runner/capabilities.py` maps required command capabilities to package
  script names and reports missing script evidence when those are absent.
- `quality_runner/audit.py` upgrades missing formatter, lint, typecheck, tests,
  dead-code, and truth file into blocker findings.
- `README.md` and `.github/workflows/ci.yml` document and run the Python gates
  directly with `pytest`, Ruff, BasedPyright, Vulture, build, and installed
  console-script smoke checks.

Impact:

Quality Runner cannot reliably audit Python projects, including itself, without
repo-specific `.quality-runner.toml` exceptions or language-aware capability
detection. This is the main Tier 1 gap because it affects the product's core
claim: evidence-backed audit findings.

Remediation:

1. Extend repository discovery to detect Python gate commands from `pyproject.toml`,
   known tool sections, CI workflow steps, and documented command blocks.
2. Add language-aware capability sources, for example `pyproject.toml:tool.ruff`,
   `pyproject.toml:tool.basedpyright`, `pytest`, `vulture`, `uv build`, and CI
   workflow commands.
3. Change missing-capability recommendations so Python repos do not receive
   `pnpm`-specific fixes.
4. Add regression tests proving Quality Runner audits this repo as having the
   Python gates that actually exist.

Verification:

- `quality-runner run . --profile jakyeamos --run-id <new-run> --json`
- Confirm the self-audit no longer emits false missing formatter, lint,
  typecheck, tests, build, dead-code, runtime-smoke, or pre-pr findings when the
  gates are discoverable from Python/CI evidence.

### P1: Pre-CR is configured but not usable as a passing local gate

`pre-cr run --workspace . --json` returns `gateDecision: block`. It loads
`.pre-cr/coverage.lcov`, but reports no changed files and no produced coverage
check. The generated LCOV summary is 1456 covered lines out of 1885 total lines,
or 77.2%, below the configured threshold of 80.

Evidence:

- `.pre-cr.json` sets `testCommand` to `python3.14 scripts/run_pytest_with_lcov.py`,
  `coveragePaths` to `.pre-cr/coverage.lcov`, and `threshold` to 80.
- The local command `python3.14 scripts/run_pytest_with_lcov.py` passes 114 tests
  and writes `.pre-cr/coverage.lcov`.
- `pre-cr run --workspace . --json` blocks with `no-changes` and reports the
  loaded LCOV line percentage as 77.

Impact:

The README and contributing guide list Pre-CR as part of the full local ladder,
but the gate does not currently provide a clean pass on an unchanged workspace.
That weakens the project's own quality-runner posture because one declared gate
cannot be used as a stable completion signal.

Remediation:

1. Decide whether Pre-CR should be a changed-lines-only gate or a full repo gate.
2. If changed-lines-only, document that it is expected to block with no changed
   files and remove it from the unconditional full-ladder wording.
3. If full repo, adjust Pre-CR configuration or coverage generation so it can
   evaluate the repo and pass when coverage meets the threshold.
4. Raise coverage above 80 or lower the threshold only with explicit rationale.

Verification:

- `python3.14 scripts/run_pytest_with_lcov.py`
- `pre-cr run --workspace . --json`
- Confirm the command returns `ok: true` for the intended usage mode.

### P2: Tier 1 release mechanics pass locally, but publishing remains blocked

Local package build and installed-wheel smoke checks pass. Release documentation
still records the PyPI Trusted Publisher setup as a pending external handoff.

Evidence:

- `uv build` successfully built `dist/quality_runner-0.1.0.tar.gz` and
  `dist/quality_runner-0.1.0-py3-none-any.whl` during the original Tier 1 pass;
  the 0.2.0 release prep must rebuild and smoke the 0.2.0 wheel before tagging.
- A clean venv installed the wheel with `pip install --no-deps`.
- Installed `quality-runner --version`, `quality-runner doctor --json`, and
  `quality-runner-mcp --version` all passed.
- `docs/release.md` says the prior `v0.1.0` release run reached publish and
  failed with `invalid-publisher`, and now requires PyPI Trusted Publisher
  verification before tagging `v0.2.0`.

Impact:

The package is locally shippable, but the release path is not complete until the
PyPI Trusted Publisher configuration exists and a tag workflow publishes
successfully.

Remediation:

1. Complete PyPI pending trusted publisher setup for the documented owner,
   repository, workflow filename, and environment.
2. Rerun the release workflow or repush the version tag.
3. Verify installation from PyPI and update release notes.

Verification:

- GitHub Actions release run completes publish.
- `uv tool install quality-runner`
- `quality-runner --version`
- `quality-runner doctor --json`

### P2: Project truth-file rule is ambiguous for this repo

The personal profile expects `.tracker/PROJECT_TRUTH.md` maintenance when a repo
has a truth file. Quality Runner's self-audit treats missing truth file as a
blocker even though this repo has no `.tracker/PROJECT_TRUTH.md` and no local
agent instruction file requiring one.

Evidence:

- `docs/standards-profiles.md` says `.tracker/PROJECT_TRUTH.md` maintenance is
  expected when a repo has a truth file.
- `quality_runner/capabilities.py` includes `truth_file` as a required file
  capability by default.
- The generated self-audit reports `missing-truth-file` as a blocker.

Impact:

This creates a policy mismatch: absence of an optional repo-state artifact is
reported as a blocker. That can train users to ignore Quality Runner blocker
findings or add low-value truth files to repos that do not need them.

Remediation:

1. Align `truth_file` with the documented rule: required only when present,
   explicitly configured, or required by a local agent contract.
2. Add a test for a repo without `.tracker/PROJECT_TRUTH.md` proving it is not a
   blocker unless configured as required.

Verification:

- `quality-runner run` on a Python fixture without a truth file does not emit
  `missing-truth-file`.
- A fixture with an explicit truth-file requirement still emits the blocker when
  absent.

## Passing Evidence

Local checks run on 2026-07-01:

| Gate | Result |
| --- | --- |
| `python3.14 -m pytest -q` | Pass, 114 tests |
| `ruff check .` | Pass |
| `ruff format --check .` | Pass, 25 files already formatted |
| `basedpyright` | Pass, 0 errors |
| `vulture . --min-confidence 70` | Pass, no findings |
| `uv run --with pytest pytest -q` | Pass, 114 tests |
| `python3.14 scripts/run_pytest_with_lcov.py` | Pass, 114 tests, LCOV written |
| `pre-cr run --workspace . --json` | Fail, gateDecision block |
| `uv build` | Pass after network access for build-system dependency resolution |
| Installed wheel smoke | Pass |
| `quality-runner run . --profile jakyeamos --run-id tier-one-self-audit-2026-07-01 --json` | Planned, false-positive capability blockers |

## Ordered Remediation Plan

1. Make capability detection language-aware and CI-aware.
2. Correct Python-specific recommendations and truth-file requirement semantics.
3. Add self-audit regression fixtures for Python projects with documented gates.
4. Decide and fix the Pre-CR usage model.
5. Complete PyPI Trusted Publisher setup and verify a successful tag release.
