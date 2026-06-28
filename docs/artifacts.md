# Artifact Contract

Artifacts are written under:

```text
<repo>/.quality-runner/runs/<run-id>/
```

`run-id` must be a single path segment. Absolute paths, separators, `.` and
`..` are rejected.

## Inspect Artifacts

`quality-runner inspect` writes:

- `repo-scan.json`: repository facts such as package scripts, lockfiles, agent
  instruction files, Pre-CR config, and project truth file presence.
- `standards.json`: compiled standards packet for the selected profile.
- `capability-matrix.json`: available and missing quality capabilities.

## Run Artifacts

`quality-runner run` writes all inspect artifacts plus:

- `quality-audit.json`: evidence-backed findings with severity, category,
  evidence, recommended fix, and verification.
- `remediation-plan.json`: ordered remediation slices with priority, actions,
  findings, and verification gates.
- `agent-handoff.json`: machine-readable next-slice handoff.
- `agent-handoff.md`: human-readable handoff for a coding agent.

## Safety Guarantees

Quality Runner rejects:

- unsafe run ids
- symlinked `.quality-runner`, `runs`, or run-directory components before writes
- symlinked artifact leaf files before writes
- symlinked handoff export paths before reads

Quality Runner v1 does not edit files outside its artifact directory.
