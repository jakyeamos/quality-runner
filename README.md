# Quality Runner

Quality Runner is a standalone audit-and-plan quality orchestrator.

Version 1 inspects a target repository, compiles applicable standards, detects available quality capabilities, writes audit artifacts, and produces an ordered remediation plan. It does not edit target source files or create commits.

## Commands

```bash
quality-runner doctor
quality-runner inspect /path/to/repo --json
quality-runner audit /path/to/repo --standards jakyeamos --json
quality-runner plan /path/to/repo --standards jakyeamos --json
quality-runner run /path/to/repo --standards jakyeamos --json
quality-runner status /path/to/repo --json
quality-runner export-handoff /path/to/repo --run-id <run-id>
```
