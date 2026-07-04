---
name: repo-quality-certifier
description: Use when a repository needs tier-one quality certification, adoption readiness classification, broad quality rubrics, gate-specific remediation planning, or generated adoption document-quality validation.
---

# Repo Quality Certifier

Use this skill to certify a repository's quality posture without relying on AIOS runtime state.

## Commands

Generate certification artifacts:

```bash
repo-quality-certifier plan --repo-root "<repo>" --run-id "<run-id>" --json
```

Generate artifacts and validate document quality:

```bash
repo-quality-certifier doc-quality --repo-root "<repo>" --run-id "<run-id>" --json
```

## MCP

Start the MCP-compatible stdio server:

```bash
repo-quality-certifier-mcp
```

Available tools:

- `repo_quality_certifier_plan`
- `repo_quality_certifier_doc_quality`

## Operating Rules

- Treat JSON artifacts as the agent-readable source of truth.
- Do not claim quality-standard compliance unless generated evidence covers the selected gate profile.
- Keep generated artifacts under `AIOS-backfill/gate-adoption/{run_id}` or an explicitly configured ignored output directory.
- Use `doc-quality` before handing generated audit or implementation docs to execution agents.
