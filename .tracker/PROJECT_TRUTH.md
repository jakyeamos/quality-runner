# Quality Runner Project Truth

Last updated: 2026-07-04

Quality Runner is the public, installable quality orchestration package. It owns
the CLI/MCP workflow for repo inspection, gate evidence, audit generation,
remediation planning, handoff export, and controller report validation.

Version `0.3.1` is the compatibility release candidate for replacing direct
`quality-evidence-contract` and `repo-quality-certifier` consumers with the
single Quality Runner package.

The package also carries compatibility surfaces for earlier extracted quality
packages when those APIs are still imported by active tools:

- `quality_evidence_contract` remains available for shared evidence and finding
  schema normalization.
- `repo_quality_certifier`, `repo-quality-certifier`, and
  `repo-quality-certifier-mcp` remain available as compatibility surfaces for
  older gate-certification callers.

New public positioning and new integrations should lead with `quality-runner`.

Current package-mining state:

- The `quality-runner` wheel includes `quality_evidence_contract`,
  `repo_quality_certifier`, both repo-quality-certifier console scripts, and
  the certifier plugin manifest/skill package data.
- `quality-runner release-smoke` now verifies compatibility imports,
  repo-quality-certifier artifact generation, certifier MCP tool metadata, and
  packaged plugin manifests.
- Release docs target `v0.3.1` and include post-install checks for the
  compatibility imports, CLI, MCP, and release smoke before archiving old repos.
