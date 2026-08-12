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

The repository change-surface matrix also owns release distribution intent.
Every applicable surface must declare `distribution` as `public_core`,
`public_adapter`, or `local_only`; a public adapter must list at least one
sanitized `contract_fixtures` path. `policy-surfaces check` treats missing
classification as incomplete evidence, while the stronger publication gate is:

```sh
uv build
qr release-boundary REPOSITORY --dist-dir REPOSITORY/dist --json
```

The release gate additionally checks tracked public content, wheel/sdist
members, adapter fixtures, and the installed wheel in an isolated home.
It persists a privacy-safe v2 receipt at
`.quality-runner/release-boundary.json` for exact-target consumers such as
Pronto. The receipt contains hashes and relative names, never workstation
paths or private inventories.
