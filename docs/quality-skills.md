# Quality Skills

Quality Skills let you attach standards you personally value to a codebase. Quality
Runner evaluates whether the repository lives up to those standards and includes
failures as normal findings in the audit and remediation plan.

Skills are **opt-in**, **local-first**, and **non-executable**. Quality Runner
does not call a model, run arbitrary skill code, or perform remediation.

## Why Quality Skills exist

Generic structural scans answer whether a repo satisfies broad code-quality
expectations. Quality Skills answer a different question:

> Does this repository reflect the standards this user or team intentionally values?

Examples include UI polish, accessibility, API design, architecture boundaries,
validation quality, test quality, product copy hygiene, and performance budgets.

## Local design

Skills are stored as local TOML packs:

```text
.quality-runner/skills/<skill-id>.toml
```

Enable them in `.quality-runner.toml`:

```toml
[quality_runner.skills]
enabled = true
active = ["ui-polish", "architecture-boundaries"]

[[quality_runner.skills.local]]
id = "ui-polish"
path = ".quality-runner/skills/ui-polish.toml"
applies_to = ["apps/web/**", "packages/ui/**"]

[[quality_runner.skills.local]]
id = "architecture-boundaries"
path = ".quality-runner/skills/architecture-boundaries.toml"
applies_to = ["**/*.ts", "**/*.tsx"]
```

Behavior:

- If `[quality_runner.skills]` is absent, no skills run.
- If `enabled = false`, no skills run.
- If `active` is present, only listed skill ids run.
- If `active` is absent, all configured local skills may run.
- Skill paths must stay inside the repo. Path traversal is rejected.
- Missing or malformed skill files are skipped safely and surfaced as warnings.

## Deterministic rules

v1 supports three deterministic rule types:

1. `disallowed_pattern` — emit a finding when a line matches a configured regex.
2. `trigger_without_required` — emit a finding when a file has a trigger pattern
   but none of the required patterns.
3. `import_boundary` — emit a finding when a source file imports a disallowed target.

Example skill pack:

```toml
id = "ui-polish"
name = "UI Polish Standards"
version = "0.1.0"
description = "Checks for interaction clarity, loading states, empty states, accessibility, and product polish."

[[deterministic_rules]]
id = "ui-clickable-div"
type = "disallowed_pattern"
category = "accessibility"
severity = "warning"
confidence = "medium"
paths = ["**/*.tsx", "**/*.jsx"]
disallowed_patterns = ["<div[^>]+onClick="]
message = "Clickable divs should usually be semantic buttons or links."
risk = "Non-semantic interactive elements hurt keyboard and assistive technology users."
expected = "Use button/link semantics or provide keyboard and ARIA support."
verification = "Rerun quality-runner and confirm this skill finding clears."
```

Skill findings use category `skill:<skill-id>` and flow through
`code-quality-scan.json`, `quality-audit.json`, `remediation-plan.json`,
`slice-specs/`, and `agent-handoff.md` like other structural findings.
The raw finding also preserves `rule_message` and `rule_category`. The scan
records `skill_coverage` with scoped files, matched files, finding counts, and
skip reasons. Deterministic rules default to `confidence = "medium"`; use
`low`, `medium`, or `high` explicitly when the rule is heuristic or exact.
Malformed rule entries remain inactive but are surfaced as configuration
warnings during ingest and scanning instead of disappearing silently.

## Agent-assisted reviews

Some standards require judgment. Skills can define `agent_reviews` rubrics. Quality
Runner compiles them into review packet artifacts:

```text
.quality-runner/runs/<run-id>/skill-review-packet.json
.quality-runner/runs/<run-id>/skill-review-packet.md
```

Quality Runner does **not** call a model. A supervising agent reads the packet,
inspects the repo, and produces a review report.

### Review report schema

```json
{
  "schema": "quality-runner-skill-review-report-v0.1",
  "run_id": "example-run",
  "reviewer": {
    "type": "agent",
    "name": "coding-agent"
  },
  "findings": [
    {
      "skill_id": "ui-polish",
      "review_id": "ui-polish-review",
      "rule_id": "ui-polish-review/missing-empty-state",
      "severity": "observation",
      "confidence": "medium",
      "file": "apps/web/src/search/results.tsx",
      "line": 42,
      "summary": "Collection UI renders results without an empty state.",
      "evidence": "{items.map((item) => <ResultCard item={item} />)}",
      "risk": "Users may see a blank or confusing screen when no results are available.",
      "expected_improvement": "Add an empty state for zero-result or unavailable-data cases.",
      "verification": "Rerun Quality Runner and confirm this skill finding clears or is dispositioned."
    }
  ]
}
```

Quality Runner validates agent-produced findings before merging them. Findings
without file, line, or evidence are rejected or ignored.
The review packet prefers high recall: agents may report plausible findings with
`observation` severity and `low` confidence when concrete source evidence exists.

### Starter pack: UI Foundations

The [UI Foundations starter pack](examples/ui-foundations.toml) consolidates the
source-auditable parts of the UI skill corpus into one pack. It keeps exact or
high-signal patterns deterministic, including decorative gradient treatments and
likely missing loading or empty states. It sends hierarchy, interaction
completeness, accessibility, and visual restraint to agent review because those
standards need context.

The pack is intentionally high-recall. Its low-confidence observations are
review prompts, not automatic proof that a design choice is wrong. Copy it into
`.quality-runner/skills/`, add it to `[quality_runner.skills.local]`, and scope it
to the repository's UI source paths before activating it.

### Starter pack: Test Strategy and Regression

The [Test Strategy and Regression starter pack](examples/test-strategy.toml)
converts the test-strategy corpus into source-level signals for skipped or
focused tests and test files without visible assertions. Its agent reviews cover
behavior and contract coverage, regression value, isolation and determinism, and
quality-gate evidence.

The deterministic checks are intentionally low-confidence observations because
test frameworks use different assertion and marker conventions. The agent
review must use repository evidence to distinguish a real coverage gap from an
intentional integration test, snapshot, fixture, or exception.

### Starter pack: Security and Privacy

The [Security and Privacy starter pack](examples/security-privacy.toml) adds
redaction-safe transport and cross-origin observations plus agent reviews for
secrets, authorization, privacy-sensitive data flows, input boundaries, and
security evidence gates.

This pack complements Quality Runner's existing security candidate scanner. It
does not reproduce secret values, attempt exploit development, or treat a
source-only signal as a confirmed vulnerability. Agent findings must redact
sensitive evidence and identify the evidence gap or boundary that requires
confirmation.

### Starter pack: Release Readiness

The [Release Readiness starter pack](examples/release-readiness.toml) adds
observations for verification bypasses and release workflows without visible
quality commands. Its agent reviews cover ship evidence, blockers, compatibility
risk, rollback and operations, and release handoff communication.

The pack treats missing evidence as a finding, but does not assume that a
configured command passed or that a repository-local workflow contains the full
deployment environment. Those conclusions remain evidence-backed agent review
questions.

### Starter pack: PR Risk and Merge Readiness

The [PR Risk starter pack](examples/pr-risk.toml) adds a high-confidence merge
conflict-marker check and agent reviews for changed-surface mapping, contract and
regression risk, scope cohesion, merge evidence, and review handoff.

The pack requires diff or PR metadata for claims about what changed. When that
metadata is unavailable, the review must report the evidence gap instead of
guessing the change surface.

### Starter pack: Data Integrity and Migration Safety

The [Data Integrity starter pack](examples/data-integrity.toml) adds observations
for destructive schema operations and migration deletes. Its agent reviews cover
invariants, migration and backfill safety, pipeline reconciliation, data-loss and
duplication risk, and verification fixtures.

The deterministic checks are signals for review, not proof that a migration is
unsafe. The agent must consider ordering, database constraints, transaction
behavior, representative data, recovery, and the repository's actual writers
before elevating a finding.

Merge a validated report during a run:

```bash
quality-runner run /path/to/repo \
  --run-id skill-audit-001-reviewed \
  --skill-review-report /tmp/skill-review-report.json \
  --json
```

Validate a report without running a full audit:

```bash
quality-runner validate-skill-review /tmp/skill-review-report.json \
  --repo-path /path/to/repo \
  --json
```

## Skill ingest

Users may have standards in natural language, markdown, or another agent skill
format. Quality Runner does not creatively interpret those inputs. Instead:

```text
Raw skill / user preference / markdown guide
        ↓
Agent-facing skill ingest prompt (docs/skill-ingest-agent.md)
        ↓
Agent converts it into QR skill TOML
        ↓
QR validates and registers the skill
        ↓
QR uses the skill in deterministic scans and/or review packets
```

Dry run:

```bash
quality-runner skill ingest /tmp/ui-polish.toml \
  --repo-path /path/to/repo \
  --id ui-polish \
  --json
```

Register and activate:

```bash
quality-runner skill ingest /tmp/ui-polish.toml \
  --repo-path /path/to/repo \
  --id ui-polish \
  --activate \
  --write \
  --json
```

Skill ingest may write QR-owned files only:

- `.quality-runner/skills/<skill-id>.toml`
- `.quality-runner.toml`

Each run records active skill identity (`id`, `version`, and content hash) in
`code-quality-scan.json` and `run-manifest.json` so later audits can be compared
against the exact skill definitions that produced them.

It must not edit application source files.

## Safety boundary

Quality Runner may:

- inspect repositories,
- run deterministic local scans,
- compile standards and skills,
- generate review packets for an agent,
- ingest validated agent-review reports,
- emit evidence-backed findings,
- write QR-owned artifacts,
- produce remediation plans and handoffs.

Quality Runner must not:

- edit target source files,
- execute remediation,
- install target dependencies,
- create commits,
- call remote services directly for review,
- run arbitrary skill code,
- apply fixes.

```text
Agent review is allowed.
Agent execution/remediation through QR is not allowed.
```

## End-to-end workflow

```bash
# 1. User gives an agent a raw skill they like.

# 2. Agent uses docs/skill-ingest-agent.md to convert it into /tmp/ui-polish.toml

# 3. Validate the candidate skill
quality-runner skill ingest /tmp/ui-polish.toml \
  --repo-path . \
  --id ui-polish \
  --json

# 4. Register and activate after approval
quality-runner skill ingest /tmp/ui-polish.toml \
  --repo-path . \
  --id ui-polish \
  --activate \
  --write \
  --json

# 5. Run with deterministic skill findings
quality-runner run . --run-id skill-audit-001 --json

# 6. QR emits skill-review-packet.* when agent reviews are configured

# 7. Agent produces /tmp/skill-review-report.json

# 8. Validate and merge the review
quality-runner run . \
  --run-id skill-audit-001-reviewed \
  --skill-review-report /tmp/skill-review-report.json \
  --json
```

See also [Skill Ingest Agent Prompt](skill-ingest-agent.md).
