# CLI Reference

Quality Runner provides two console scripts:

- `quality-runner`
- `quality-runner-mcp`

## `quality-runner doctor`

Checks local install readiness.

```bash
quality-runner doctor --json
```

Returns:

- schema: `quality-runner-doctor-result-v0.1`
- status: `ready`
- package version
- local Python/platform details

## `quality-runner inspect`

Inspects repo shape, standards, and quality capability signals without producing
audit or remediation artifacts.

```bash
quality-runner inspect /path/to/repo --run-id inspect-001 --json
quality-runner inspect /path/to/repo --ci-status-json ci-status.json --json
```

The standards profile defaults to `default`; use `--profile` only to select a
saved custom profile or override repo config.

Writes:

- `repo-scan.json`
- `code-quality-scan.json`
- `standards.json`
- `capability-matrix.json`

## `quality-runner init`

Writes a starter `.quality-runner.toml`.

```bash
quality-runner init /path/to/repo \
  --required-capability lint \
  --required-capability tests \
  --json
```

Use `--force` to replace an existing config.

The same config file can add repo-specific scan exclusions:

```toml
[quality_runner]
scan_exclusions = ["samples", "generated-reports/**"]
```

These augment the default exclusions for fixtures, corpora, docs, vendored
trees, and tool output directories.

## `quality-runner status`

Reports the normalized repo config and latest run metadata.

```bash
quality-runner status /path/to/repo --json
```

## `quality-runner run`

Runs the full audit-and-plan workflow.

```bash
quality-runner run /path/to/repo --run-id baseline-001 --json
quality-runner run /path/to/repo --ci-status-json ci-status.json --json
```

The standards profile defaults to `default`; use `--profile` only to select a
saved custom profile or override repo config.

Writes:

- `repo-scan.json`
- `code-quality-scan.json`
- `standards.json`
- `capability-matrix.json`
- `quality-audit.json`
- `remediation-plan.json`
- `resolution-ledger.json`
- `resolution-ledger.md`
- `agent-handoff.json`
- `agent-handoff.md`

## `quality-runner export-handoff`

Prints the latest `agent-handoff.md`, or a selected run handoff.

```bash
quality-runner export-handoff /path/to/repo
quality-runner export-handoff /path/to/repo --run-id baseline-001 --output handoff.md --json
```

## Exit Behavior

- `0`: command completed successfully.
- `1`: validation or filesystem error.
- `2`: argument parsing error.

Errors are printed to stderr without Python tracebacks.
