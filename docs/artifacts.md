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
  instruction files, language-aware quality commands, mature repo surfaces,
  nested workspaces, ecosystems, generated-code markers, local CI checks,
  Pre-CR config, and project truth file presence.
- `code-quality-scan.json`: deterministic structural/code-quality findings,
  line accountability, duplicate clusters, skipped generated/vendor paths, and
  non-blocking remediation buckets.
- `standards.json`: compiled standards packet for the selected profile,
  including saved custom profile settings when a repo-defined profile is used.
- `capability-matrix.json`: available and missing quality capabilities.
  Available command-backed capabilities include the command, source, detected
  language, optional owner/severity policy, required-by provenance, and local CI
  status evidence.
- `run-manifest.json`: run metadata, Quality Runner version, artifact paths, and
  git HEAD/branch/dirty state when the target is a git repo.

## Run Artifacts

`quality-runner run` writes all inspect artifacts plus:

- `quality-audit.json`: evidence-backed findings with severity, optional owner,
  category, evidence, recommended fix, and verification.
- `remediation-plan.json`: ordered remediation slices with priority, actions,
  findings, and verification gates.
- `resolution-ledger.json`: current finding lifecycle state by stable
  fingerprint, preserving accepted dispositions and marking disappeared
  findings fixed on later runs.
- `resolution-ledger.md`: human-readable resolution ledger summary.
- `agent-handoff.json`: machine-readable next-slice handoff.
- `agent-handoff.md`: human-readable handoff for a coding agent.

## Safety Guarantees

Quality Runner rejects:

- unsafe run ids
- symlinked `.quality-runner`, `runs`, or run-directory components before writes
- symlinked artifact leaf files before writes
- symlinked handoff export paths before reads

Quality Runner v1 does not edit files outside its artifact directory.

## Compatibility Policy

Artifact schema ids stay on `v0.1` while changes are additive and old consumers
can continue to read previous fields unchanged. New optional fields may appear
in artifacts and schemas, but existing required fields keep their meaning.

A schema id must move to the next minor version before a release that removes a
field, changes a field meaning, changes a required field type, or makes an
optional field required.

## Local CI Status

`quality-runner inspect` and `quality-runner run` accept
`--ci-status-json <path>` for a local export shaped as:

```json
{
  "checks": [
    {
      "name": "Quality / Lint",
      "status": "completed",
      "conclusion": "success",
      "url": "https://example.invalid/check"
    }
  ]
}
```

The file must live inside the target repo and is read as evidence only. Quality
Runner does not call GitHub, fetch live check runs, or execute commands from CI
configuration.
