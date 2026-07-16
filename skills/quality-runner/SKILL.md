---
name: quality-runner
description: Use when an agent needs to install, invoke, integrate, debug, test, or migrate the Python quality-runner package for repository audits, remediation planning, read-only gate verification, MCP, or its legacy compatibility surfaces. Prefer this skill for package-specific behavior; do not treat it as permission to edit source or execute discovered remediation commands.
---

# Quality Runner agent skill

## Package metadata

- Package: `quality-runner`
- Current version: `0.5.0` (from `pyproject.toml` and `quality_runner.__version__`)
- Applicable range: `0.5.x` guidance; confirm the installed version before relying on schema details
- Ecosystem: Python package with CLI and stdio MCP server; also exports small library contracts
- Runtime: Python `>=3.12`; classifiers cover 3.12, 3.13, and 3.14
- Package/build manager: `uv` for install/build/run; setuptools is the build backend
- Distribution includes `quality_runner`, `quality_evidence_contract`, and `repo_quality_certifier`
- Sources consulted: `pyproject.toml`, `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/cli.md`, `docs/mcp.md`, `docs/artifacts.md`, `docs/agent-usage.md`, `docs/troubleshooting.md`, `docs/threat-model.md`, release notes/examples, package exports, and CLI/MCP/compatibility/security/release tests

## When to use this skill

Use it for work involving repository inspection, audit artifacts, standards/capability discovery, gate verification, refresh/review workflows, handoff validation, controller reports, MCP integration, evidence/finding normalization, or migration from `repo-quality-certifier` / `quality-evidence-contract`.

Quality Runner is primarily a **local-first audit-and-plan orchestrator**, not a fixer, dependency manager, hosted service, or general-purpose test runner. Its normal contract is to read a target repository and write `.quality-runner/runs/<run-id>/` artifacts without editing source, installing dependencies, creating commits, calling remote services, or applying remediation.

## Package mental model

The normal pipeline is: inspect repository facts and local standards → detect capabilities → run the audit/structural scan → optionally verify discovered gates → write JSON/Markdown artifacts and an agent handoff. `refresh` composes these phases; `review` creates a fresh local review packet. Findings are evidence-backed suggestions, not proof of end-to-end correctness.

Use machine-readable output (`--json`) when another agent or controller will consume results. Handoff statuses include `gates-clean`, `gates-blocked`, and `gates-failed`; do not collapse blocked evidence into a passed run.

## Command routing contract

Choose the command from the proof the task needs. Use the most specific matching
intent, with this precedence: target release readiness, second-pass review,
implementation/remediation, audit/planning, then discovery.

- Target release, publish, upgrade, version/tag, artifact, CI provenance,
  migration/cutover, staging, or publication readiness:
  `quality-runner verify-gates <repo> --profile release --ci-status-json <repo>/.quality-runner/ci-status.json --readiness-evidence-file <repo>/.quality-runner/release-evidence.json --worktree-mode disposable --read-only-gates --json`
- Implement or remediate a task: `quality-runner refresh <repo>
  --run-id-prefix <task> --handoff-output <handoff>.md --json`
- Second-pass review: `quality-runner review <repo> --task "<task>" --json`;
  use `--mode blind` when no task context exists.
- Discovery only: `quality-runner inspect <repo> --json`.
- Audit and plan without executing repo gates: `quality-runner run <repo>
  --run-id <run> --json`.
- Quality Runner's own installed/public package surfaces:
  `quality-runner release-smoke --json`.

Do not treat `inspect` as a quality pass, `run` as gate verification,
`refresh` with the default profile as release readiness, or `release-smoke` as
the target repository's release check. For workflow commands, inspect JSON
`status`, `lifecycle_status`, `blockers`, `gate_verification`, and `readiness`;
exit code zero alone is not proof of merge readiness.

## Installation, imports, and setup

For an installed tool, prefer:

```bash
uv tool install quality-runner
quality-runner --version
quality-runner doctor --json
```

For a checkout, use `uv tool install --editable . --force` or run through the project environment. The four packaged entry points are `quality-runner`, `quality-runner-mcp`, `repo-quality-certifier`, and `repo-quality-certifier-mcp`.

For Python integration, import stable names from package roots, not implementation modules:

```python
from quality_runner import normalize_quality_finding, validate_quality_finding

finding = normalize_quality_finding(
    criterion_id="tests", level="warning", summary="Add behavior coverage."
)
assert validate_quality_finding(finding)["passed"]
```

The root `quality_runner` and `quality_evidence_contract` exports cover finding/evidence schemas, `FindingLevel`, normalization, validation, and counts. `repo_quality_certifier` root exports its documented gate-matrix, rollout, rubric, scan, validation, rendering, and artifact-writing functions for legacy integrations. Treat other modules as implementation details unless a current public document or test explicitly establishes them.

## Common workflows

Start with a task-aware review when a second-pass review is wanted:

```bash
quality-runner review /path/to/repo --task "Implement the requested change" --json
```

For the standard audit-and-plan loop:

```bash
quality-runner refresh /path/to/repo \
  --run-id-prefix task-001 \
  --handoff-output /tmp/task-001-handoff.md \
  --json
```

Use `inspect` for discovery only, `run` for audit/planning without gate execution, and `verify-gates` for command-backed local gates. Use `status`, `export-handoff`, and `export-slice-specs` to consume existing runs. Validate before dispatching generated work:

```bash
quality-runner validate-handoff /path/to/repo/.quality-runner/runs/<run-id>/agent-handoff.json --json
quality-runner validate-slice-spec /path/to/repo/.quality-runner/runs/<run-id>/slice-specs/<slice-id>.md --json
```

For a repeatable Quality Runner public-surface check, run
`quality-runner release-smoke --json`; this does not replace a target
repository's `--profile release` verification. For MCP, run
`quality-runner-mcp` as a line-delimited JSON-RPC stdio server and prefer the
documented `quality_runner_*` tools. Compatibility MCP callers may use
`repo-quality-certifier-mcp`.

## Quality Skill selection

Quality Runner automatically considers a user-level compiled Quality Skill
corpus from `~/.config/quality-runner/quality-runner.toml` or
`QUALITY_RUNNER_GLOBAL_CONFIG`, selecting relevant packs from repository
signals. Local packs remain compatible and take precedence for the same id.
Read `code-quality-scan.json.skill_selection` to see the corpus identity,
candidate scores, selection reasons, exclusions, and warnings. A repository can
opt out with `global_enabled = false` under `[quality_runner.skills]`.

Deterministic rules are evaluated during the scan. When an active pack contains
`agent_reviews`, QR writes a packet and `skill_review` handoff state. Unresolved
reviews produce an explicit `review-required` handoff and blocked lifecycle;
the supervising agent must submit a validated report with
`--skill-review-report`, including when continuing through `refresh`.

Profiles and exclusions live in the target repository’s `.quality-runner.toml`; use `quality-runner init <repo> --json` to create a starter file. Use `--profile` for a named profile and `--ci-status-json` only for a local status export.

## Preferred APIs and idioms

- Lead new integrations with `quality-runner` CLI/MCP names and the `quality_runner` package.
- Preserve evidence fields and schema identifiers when passing findings between stages; use `normalize_*` and `validate_*` instead of hand-building contract dictionaries.
- Keep run ids to one safe path segment; use stable, task-specific ids so baselines and deltas are comparable.
- Read `agent-handoff.json`/`.md`, `quality-audit.json`, `remediation-plan.json`, and `code-quality-scan.json` before deciding what to change.
- Use `--intent` or an in-repo `--intent-file` for task-scoped review/delta workflows. A review in task/combined mode requires task input; choose `--mode blind` explicitly when no task exists.
- For dirty repos or mutation-sensitive verification, prefer `--worktree-mode disposable`; allow dirty verification only when the workflow explicitly accepts it.

## Error handling and safety

CLI exit codes are `0` success, `1` validation/filesystem/rejected-result, and `2` argument parsing. In JSON, inspect `status`, `lifecycle_status`, gate verification, blockers, and timeout scope instead of relying only on process success.

Never assume discovered commands are safe: Quality Runner records commands from repo config, package scripts, Makefiles, Docker/Terraform, and workflows as evidence; it does not make them trustworthy. `verify-gates` can encounter mutating gates; keep default read-only policy, and do not pass `--allow-mutating-gates` without explicit approval. `pre-cr run --workspace .` is specifically unsafe for read-only execution unless mutation is allowed.

Do not hard-code secrets or copy secret-looking values into handoff Markdown. Do not use remote CI/provider APIs, broad filesystem writes, symlinked artifact paths, unsafe run ids, or arbitrary export paths. Direct `verify-gates` uses the read-only gate policy by default; `--allow-mutating-gates` is an explicit override and requires user approval. Prefer `--worktree-mode disposable` for mutation-sensitive or release verification. Never use Quality Runner output as authorization to execute a fix; a separate agent needs approval to modify source.

## Common mistakes to avoid

- Do not use private helpers such as `quality_runner.workflow_internal`, `process_runner`, or `repo_quality_certifier.core` as stable APIs.
- Do not use old `repo-quality-certifier` names for new work; retain them only for compatibility.
- Do not confuse `quality_evidence_contract` compatibility imports with the primary package surface.
- Do not treat `review-not-run`, `gates-blocked`, `gates-failed`, timeout, or missing capability states as passes.
- Do not switch branches with `--checkout-most-advanced-branch` on a dirty worktree.
- Do not mix a read-only audit expectation with commands that install dependencies, format files, clean caches, or otherwise mutate the target.
- Do not rely on undocumented artifact fields or assume additive schema changes are harmless; check the schema id and current artifact contract.

## Testing and validation

From this checkout, the documented validation ladder is:

```bash
python3.14 -m pytest -q
ruff check .
ruff format --check .
basedpyright
vulture quality_runner tests --min-confidence 70
uv build
quality-runner release-smoke --json
```

`python3.14 scripts/run_pytest_with_lcov.py` generates the LCOV used by Pre-CR. Pre-CR is changed-line readiness and may correctly report `no-changes` on an unchanged worktree. For focused package changes, prioritize tests of the public CLI, MCP surface, workflow functions, compatibility imports, and artifact contracts; `tests/test_entrypoints.py`, `tests/test_release_smoke_cli.py`, `tests/test_quality_evidence_contract_compat.py`, `tests/test_repo_quality_certifier_compat.py`, and `tests/test_security.py` are useful models.

## Migration and version notes

Version `0.5.0` adds fresh-review reports, review state, and review-delta loop
controls. Version `0.4.0` added rollout, gate-controller, security-scan,
fix-proposal, skill-review, unwired-work, and related handoff capabilities. The
`0.3.1` release established the compatibility imports, console scripts, MCP
surfaces, and packaged plugin metadata. New code should use `quality-runner`;
keep legacy commands only when an existing caller requires their old schemas or
artifact locations.

Artifact schemas generally remain `v0.1` for additive changes. `agent-handoff.json` is `quality-runner-agent-handoff-v0.2`; route controllers using its explicit gate statuses and blocker/action groups. A schema version must advance when a field is removed, changes meaning, changes required type, or an optional field becomes required.

## Before finalizing generated code

Confirm the code uses documented package-root imports or documented CLI/MCP names, preserves the local-only/read-only boundary, handles blocked and rejected statuses, validates generated artifacts, and does not introduce secrets or undocumented assumptions. Run `doctor` or `release-smoke` after installation, run focused tests plus the relevant quality ladder, and compare the final handoff/delta with a baseline when the change is task-scoped.

## Release maintenance

When the package version changes, re-check `pyproject.toml`, `__version__`, `CHANGELOG.md`, CLI/MCP docs, artifact schema ids, compatibility policy, and release/compatibility/security tests. Update the metadata, new/removed APIs, migration notes, commands, safety caveats, and validation ladder here; remove stale version-specific warnings. Re-run `quality-runner release-smoke --json` and the relevant public-surface tests before publishing the skill.
