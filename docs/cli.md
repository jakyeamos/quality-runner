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
quality-runner inspect /path/to/repo --profile jakyeamos --run-id inspect-001 --json
```

Writes:

- `repo-scan.json`
- `standards.json`
- `capability-matrix.json`

## `quality-runner run`

Runs the full audit-and-plan workflow.

```bash
quality-runner run /path/to/repo --profile jakyeamos --run-id baseline-001 --json
```

Writes:

- `repo-scan.json`
- `standards.json`
- `capability-matrix.json`
- `quality-audit.json`
- `remediation-plan.json`
- `agent-handoff.json`
- `agent-handoff.md`

## Exit Behavior

- `0`: command completed successfully.
- `1`: validation or filesystem error.
- `2`: argument parsing error.

Errors are printed to stderr without Python tracebacks.
