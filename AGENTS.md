# Agent operating contract

Read `.agents/context/README.md` before non-trivial work, then load only the
packet that matches the task.

- Quality Runner is a local-first audit-and-plan orchestrator. It may write
  `.quality-runner/runs/<run-id>/` evidence in a target repository, but it must
  not edit source files, install dependencies, create commits, call providers,
  use remote services, or execute remediation.
- Use the locked `uv` environment and the commands in
  `.agents/context/commands.md`. Keep quality results evidence-backed; an
  unavailable or stale gate is `unknown` or `blocked`, never green.
- Preserve public contracts, schemas, fixtures, redaction boundaries, and
  compatibility surfaces. Do not put credentials, raw prompts, transcripts,
  private paths, or unpublished evidence in tracked files.
- Release, tagging, PyPI publication, Homebrew changes, and remote mutations
  require explicit human approval. Roll back with `git revert` or a prior
  published version; never rewrite release history.
- Keep source changes behavior-focused and add tests for public CLI, MCP,
  workflow, artifact, or schema behavior. Do not weaken a gate to remove a
  finding.

The environment contract is executable through
`python3 scripts/check_environment_contract.py` and is required by
`.pre-cr.json`. Always-loaded instructions remain boundaries and routing
pointers; detailed procedures live in the context packets.
