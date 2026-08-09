# Policy surface validation

Quality Runner inventories policy artifacts instead of treating them as
ordinary source files. `.pre-cr.json`, `.quality-runner.toml`, `.gitleaks.toml`,
and repository change-surface matrices are excluded from Python changed-line
coverage because line execution is not meaningful evidence for declarative
policy.

They are still required to pass their artifact-specific validators. Run:

```sh
qr policy-surfaces check REPOSITORY --json
```

Each report records `surface_kind: policy_config`,
`source_line_coverage: not_applicable`, and
`coverage_disposition: validated_by_policy_gate`. A malformed or stale policy
artifact fails the command; it is never silently ignored.
