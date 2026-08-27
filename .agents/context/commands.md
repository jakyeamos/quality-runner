# Canonical commands and quality gates

Last reviewed: 2026-08-24

Run from the repository root with the locked development environment:

```sh
uv sync --locked --all-groups
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked basedpyright
uv run --locked vulture quality_runner quality_evidence_contract repo_quality_certifier tests scripts --min-confidence 70
uv run --locked pip-audit
uv build
python3 scripts/check_environment_contract.py
gitleaks detect --source . --no-banner --redact
uv run --locked qr onboarding check /path/to/repository \
  --matrix ~/.agents/repository-onboarding-change-matrix.json \
  --evidence /path/to/repository/.quality-runner/onboarding-evidence.json \
  --json
uv run --locked qr fleet audit run --all \
  --projects-root /path/to/projects \
  --standard cache-design --json
uv run --locked qr fleet audit run --all \
  --projects-root /path/to/projects \
  --standard matrix-maintenance --json
```

The onboarding command is read-only unless `--output` is explicit and exits
nonzero for every non-ready state. See `docs/repository-onboarding.md` for the
versioned evidence and receipt contracts.

For a registry-owned high-confidence fleet measurement, use an exact reviewed
`quality-runner-fleet-scope/v1` manifest and run:
The scoped `matrix-maintenance` and `cache-design` lanes write a private
`standard-report.json` with every audited repository and its honest state.
A standard-scoped snapshot is intentionally not publishable as the canonical
all-standards maturity feed; replay it and inspect the report directly. Fleet
dynamic execution prefers root aggregate gates, fails closed on unbounded
package-only surfaces, honors repository gate timeouts only within the CLI
ceiling, and never runs discovered mutating or unknown-risk formatters.

```sh
uv run --locked qr fleet audit run --scope-manifest /path/to/fleet-scope.json \
  --projects-root /bounded/root --dynamic --no-changed-only --json
uv run --locked qr fleet audit replay --audit-id AUDIT_ID --json
uv run --locked qr fleet audit feed --audit-id AUDIT_ID --json
uv run --locked qr fleet certify --scope-manifest /path/to/fleet-scope.json \
  --projects-root /bounded/root --parallelism 8 --json
```
`matrix_maintenance` and `cache_design` are canonical dimensions of the complete fleet audit.
It contributes to each applicable repository's `dimension_scores`,
`maturity_score`, `dimension_gaps`, fleet means, and Pronto maturity
remediation. The scoped command above is a diagnostic slice; after it identifies
gaps, rerun the complete audit without `--standard`, pass replay, publish that
feed, and refresh Pronto before claiming the score or remediation queue reflects
the latest evidence.

The complete `fleet audit run` includes the bounded static Mac Control lane by
default. `fleet audit feed` then publishes the QR maturity feed and a
`quality-runner-maturity-checkpoint/v1` pointer bound to the same audit time,
repository population, and primary observed commits. Use `--no-mac-control`
only for an explicitly legacy or diagnostic feed; `--mac-control-live` opts
into live Mac Control checks in that same checkpoint. Consumers must treat a
missing pointer as legacy separate-feed evidence and an invalid pointer as
blocked, never as permission to mix the two stable sidecars.
`cache_design` is a non-release-blocking pilot under governance and
sustainability. It measures lifecycle classification, safe rebuildability,
bounds, duplication, and growth evidence; raw bytes alone never reduce a score.
The audit is read-only, never follows symlinks, and never executes cleanup or
repository-supplied commands. Add literal repository-relative custom surfaces
with `[[quality_runner.cache_design.paths]]`; a `bounded` lifecycle requires at
least one of `max_bytes`, `max_entries`, or `max_age_days`.

The published feed is `quality-runner-maturity-feed/v2`. Its repository score
flows from dimensions to explicit capabilities to seven weighted pillars, not
from the count of flat findings. Use `repository_maturity.pillars` and their
`capabilities` for the quality vector and
`repository_maturity.evidence` for measurement coverage, freshness, conditional
applicability, and unmapped dimensions. Conditional capabilities preserve
`applicable`, `not_applicable`, or `unknown` state. `source_dimension_mean`
is retained only for migration diagnostics. Only a finding with
`confirmed_critical_risk: true` in correctness, security, or operability
applies the score cap; blocker/P0 state alone remains a quality-outcome signal.
Agent growth health is diagnostic and does not add a fifth score beside the
four consolidated human/agent capabilities.

Use `qr fleet certify` for the complete read-only proof projection with
explicit numeric certification totals. Add `--audit-id AUDIT_ID` to reuse an
immutable audit without rerunning repository gates.

Fleet subprocess stdout and stderr are captured as UTF-8 with replacement for
malformed bytes. This preserves a bounded, redacted command receipt when a
repository tool emits non-UTF-8 output instead of aborting the coordinator.

Fleet audit publication requires `audit_coverage.status: complete` for every
repository. Unique local or remote-tracking work, dirty worktrees, ambiguous
detached commits, and stale targets remain exact-target coverage qualifiers.
Use `--allow-incomplete-coverage` only for a diagnostic feed; its
`comparison_eligible` field remains false and consumers must not rank it.

For release preparation, build both archives and run
`uv run --locked quality-runner release-boundary . --dist-dir dist --json`.
Every applicable change-matrix surface must be classified as `public_core`,
`public_adapter`, or `local_only`; public adapters require sanitized contract
fixtures, and local operator wiring must not ship. The command persists
`.quality-runner/release-boundary.json` using schema v2. Release consumers must
require its exact branch and commit, matching matrix and artifact digests, and
all checks passed; v1, stale, dirty, or missing evidence is not releasable.

For the complete pre-release path, also run:

```sh
uv run --locked python scripts/run_pytest_with_lcov.py
uv run --locked qr release-smoke --json
```

`pre-cr run --workspace . --json` is a changed-line readiness check. It is
expected to report `no-changes` on an unchanged checkout; it is not a
replacement for the full ladder above. CI and release workflows are the
authoritative remote declarations of the same gates.

`.quality-runner.toml` declares the security dependency audit and environment
contract as required blocker gates. The local checker and both remote workflows
must remain in agreement with that declaration.

The repository commit hook uses `hookTimeoutSeconds: 360` in `.pre-cr.json`.
This budget covers the traced changed-line runner on this repository; lower it
only after a measured replacement run establishes a smaller safe bound.

Quality commands must be bounded and offline-capable. They must not publish,
deploy, tag, push, call a provider, collect credentials, or execute a
remediation action. If a dependency cache, tool, or gate is unavailable, keep
the result visible as unknown or blocked.

For task-scoped implementation feedback, capture a baseline before edits, use
`uv run --locked qr task check /path/to/repository --task-id ID --fast --json`
at meaningful boundaries, and run
`uv run --locked qr task release-check /path/to/repository --task-id ID --json`
before completion. Fast mode skips certified native gates and is never
release-ready; release-check fails unless
`release_readiness.eligible: true`.

BasedPyright is certified over the declared package scope in standard mode.
Repository-wide strict mode is not certified: the 0.7.0 fold exposed a large
existing backlog when the environment branch enabled it without end-to-end
proof. Keep that migration visible as candidate work, fix findings at their
source, and do not add broad ignores or replace errors with casts.

For missing Pronto findings evidence, use `qr fleet detector refresh --all
--projects-root ROOT --json`. This explicit lane runs full deterministic
skill-pack analysis at each exact committed target, publishes only normal QR
run evidence below repository `.quality-runner/runs`, and records every
published, blocked, or unsupported repository. It does not execute discovered
gates. Missing phase artifacts remain unpublished while the fleet ledger keeps
compact phase status, timeout, and reason diagnostics. Follow with `pronto
quality refresh --json` unless Pronto owns the combined invocation.
