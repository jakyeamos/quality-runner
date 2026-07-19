# Troubleshooting

## `quality-runner` is not found

Use the source-first invocation documented in
[Consumer Tooling](consumer-tooling.md) when the repository needs the current
QR. If a persistent standalone tool is required, install the repository source:

```bash
uv tool install git+https://github.com/jakyeamos/quality-runner.git
```

Then ensure the uv tool bin directory is on PATH:

```bash
echo "$PATH"
uv tool dir
```

On this machine, console scripts are exposed through `~/.local/bin`.

## Package build fails with top-level package discovery

Quality Runner explicitly packages only `quality_runner*`. Test helpers under
`test_support/` are not included in the distributable wheel.

Run:

```bash
uv build
```

## Pre-CR reports no coverage result

Quality Runner uses a custom LCOV helper:

```bash
python3.14 scripts/run_pytest_with_lcov.py --changed-only
pre-cr run --workspace .
```

The commit hook uses `--changed-only` to select tests associated with staged
source modules. Run the wrapper without that flag for the full LCOV suite.

Documentation, workflow files, tests, and packaging metadata are excluded from
changed-line coverage surfaces.

## A run writes findings for missing repo-owned gates

That is expected. Quality Runner reports repo-owned quality gates it cannot
detect, such as lint, typecheck, tests, build, dead-code checks, Pre-CR, and
truth-file maintenance. These are separate from runner-provided structural
checks, which Quality Runner performs itself during the scan.

The tool does not install dependencies or create repo scripts automatically.
Review `agent-handoff.md` for suggested commands to add, or document an accepted
exception in `.quality-runner.toml` when a gate is intentionally absent. For
worker dispatch, validate the handoff and slice spec before editing:

```bash
quality-runner validate-handoff .quality-runner/runs/<run-id>/agent-handoff.json --json
quality-runner validate-slice-spec .quality-runner/runs/<run-id>/slice-specs/<slice-id>.md --json
```

## A generated artifact might contain sensitive data

Treat the run as local evidence and stop sharing or committing its artifacts
until it has been reviewed. If a real credential appears, rotate or revoke it
using the owning service's process, preserve only the minimum evidence needed
for the incident, then apply the repository's normal retention policy. The
security and code-quality scanners redact quoted literals in secret-like source
evidence and remediation excerpts; other source-derived context and authorized
gate output can still be sensitive.
See [Artifact Handling](artifacts.md#handling-generated-artifacts).

## A Fresh Review response is rejected

Read the saved `review-execution.json` and adapter-attempt artifact for the
reported binding or validation error. Correct the response against the original
packet-bound template and resubmit it with the same run id. If the task or
evidence boundary has changed, prepare a new review instead of altering the
saved context.

## I need to roll back an upgrade

Do not delete `.quality-runner/` artifacts to roll back the executable. Keep
the evidence, install the prior package version, and verify the result with
`quality-runner doctor --json`. The exact supported procedure and v1/v2 command
mappings are in the [Upgrade and Compatibility Guide](upgrade.md).
