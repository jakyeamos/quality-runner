# Quality Runner

Quality Runner is a standalone audit-and-plan quality orchestrator.

Version 1 inspects a target repository, compiles applicable standards, detects available quality capabilities, writes audit artifacts, and produces an ordered remediation plan. It does not edit target source files or create commits.

## Commands

```bash
quality-runner doctor
quality-runner inspect /path/to/repo --profile jakyeamos --json
quality-runner run /path/to/repo --profile jakyeamos --json
quality-runner-mcp
```

The MCP server exposes `quality_runner_doctor`, `quality_runner_inspect_repo`,
`quality_runner_run`, `quality_runner_status`, and
`quality_runner_export_handoff`.

## v1 Safety Boundary

Quality Runner v1 may create or update files under `.quality-runner/runs/<run-id>/`
in the target repository. It must not edit source files, install dependencies,
create commits, call remote services, or execute remediation.

Every generated remediation slice includes verification guidance, but a separate
coding agent must receive user approval before implementation.
