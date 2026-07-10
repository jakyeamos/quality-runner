# Phase 2: Fresh Review - Context

**Gathered:** 2026-07-09
**Status:** Ready for planning
**Source:** PRD Express Path (docs/fresh-review-prd.md)

<domain>
## Phase Boundary

Deliver the local-first Quality Runner Fresh Review workflow for solo developers
using AI coding agents. The phase includes fresh task-aware, fully blind, and
combined review context packaging; local report artifacts; known-issue and
resolution state; separate fixing-agent handoff; and read-only safety
enforcement. It does not turn the reviewer into a source editor, hosted service,
new model provider, or automatic remediation engine.

</domain>

<decisions>
## Implementation Decisions

### Product and safety boundary

- The first audience is solo developers using AI coding agents.
- Fresh Review is a CLI/MCP-adjacent extension of Quality Runner.
- The reviewer reports evidence-backed defects, credible suspicions, project
  risks, and missing evidence; it does not edit source files or execute fixes.
- The workflow remains local-first and must not silently transmit project
  content to a remote service.
- The reviewer must not install dependencies, commit, create pull requests, or
  execute remediation.

### Command and review modes

- The primary command is `quality-runner review <repo-root> [options]`.
- Default mode is task-aware fresh adversarial review.
- Supported modes are `task`, `blind`, and `combined`.
- Task mode requires an original task from inline text, a task file, or saved
  task reuse; without one it must offer blind review instead of judging task
  satisfaction.
- Blind mode must not receive the original task, prior implementation-agent
  conversation, prior reasoning, self-review, or prior review reports.
- Combined mode runs task and blind packets independently and groups overlaps
  only after both reviews complete.
- Supported scopes are task and project. Project breadth is focused, related,
  or full, with related as the default.
- Related scope includes changed areas, nearby routing/navigation,
  permissions/access paths, related data flow, and nearby project patterns.
- Focused scope prioritizes changed files and direct dependencies. Full scope
  scans the project subject to configured exclusions and practical limits.
- Users can provide exclusions, optional previous-agent summary, local evidence,
  detail level, save preference, and JSON output.

### Freshness and context packets

- Every review pass receives a newly constructed input packet and a new agent
  invocation/session.
- Task packets include the task, current repository/git state, changed files or
  diff metadata when available, selected scope/breadth, exclusions, evidence,
  and known issues only after normal-run verification.
- Blind packets include repository/git state, changed areas, scope/breadth,
  exclusions, and evidence, but no task or inherited reasoning.
- Previous agent summaries are opt-in only.
- Prior review documents are excluded from the reviewer during an active loop.
- Combined-mode reviewers must not see each other’s findings before completion.
- Freshness is a context-packaging guarantee, not a claim about hidden model
  memory; the manifest records provenance and hashes without hidden reasoning.

### Agent integration

- Quality Runner owns orchestration, packet construction, artifact validation,
  and local persistence.
- The selected BYO agent owns model execution and its native permission flow.
- The adapter contract creates a fresh invocation, returns structured JSON when
  available plus raw output, requests optional evidence through native
  permissions, and reports unavailable capabilities without false findings.
- The first implementation supports a local adapter plus a file-based adapter
  that writes a packet and reads a returned report.
- If no adapter is available, the command writes a validated shareable packet and
  explicitly says that a review did not occur.
- Quality Runner does not implement a universal permission model.

### Reports and findings

- Every saved report has human-readable Markdown and agent-friendly JSON.
- The summary uses `Review complete: X critical, Y high, Z medium issues found.`
- Required sections are executive summary, missed requirements, confirmed
  issues, suspected issues, not enough evidence, project consistency risks,
  regression risks, known accepted issues, suggested fixes, agent handoff
  prompts, and remaining uncertainty/unreviewed areas.
- Missed requirements is present even when empty for task-aware reports.
- Each finding has a stable id/fingerprint, severity, classification, explanation,
  impact, evidence/location, human fix, fixing-agent prompt, confidence, human
  confirmation flag, and status.
- Severity is critical/high/medium/low. Classification is confirmed, suspected,
  not-enough-evidence, or known-accepted. Confidence is high/medium/low and is
  independent from severity.
- Fix prompts ask a fixing agent to investigate, stay in scope, obtain approval
  before edits, and verify; they do not prescribe uncertain implementations.
- No-issue reports include: `No major issues found from available evidence, but
  this does not prove the feature works end-to-end.`
- Reports are saved by default under `.quality-runner/runs/<run-id>/`, with a
  no-save option that states no shareable report was written.

### Artifacts and state

- Review artifacts extend the existing run directory with review manifest,
  context, machine report, Markdown report, agent packet, and fix prompts.
- The machine report is canonical; Markdown renders the same normalized findings.
- The manifest records schema, timestamps, git state, mode, scope, breadth,
  exclusions, evidence references, adapter, freshness policy, and input hashes.
- Hidden model reasoning is never stored in the manifest or report.
- Human-facing statuses are open, resolved, accepted, needs-confirmation, and
  not-enough-evidence; richer machine transition metadata may be retained.
- Known issues are stored locally, shown before normal runs, and can be accepted,
  edited, or removed. Repeated known issues remain visible as previously
  accepted. Loop runs do not interrupt for known-issue verification.
- Major-change re-verification occurs after baseline/default-branch changes,
  changes outside prior in-scope paths, changes to high-risk paths (routing,
  auth/permissions, schemas/migrations, deployment), or explicit user request.
- Resolution uses existing ledger concepts, stable fingerprints, and cycle ids.
  Cross-report matching is disabled during active loops and allowed only in the
  end-of-cycle summary. Automatic resolution cannot be final without evidence.

### Implement-review loop

- The user starts the loop manually.
- Each cycle runs a fresh review, saves the report, hands selected findings (or
  an explicit critical/high shortcut) to a separate fixing agent, waits for the
  fixing result, and starts a new fresh review without prior review context.
- Stop conditions are no critical/high findings or no issues at all.
- Known-issue verification is deferred until the cycle ends.

### Evidence and privacy

- Reviewers may use repository files, diffs, project intent files, screenshots,
  test output, app behavior notes, and selected-agent capabilities.
- Evidence that is unavailable must be distinguished from evidence checked and
  found negative.
- Local path exclusions and a configurable redact list are required before
  persistence or handoff.
- Runtime/browser/computer access is optional and adapter-owned, not required
  for the core workflow.

### Claude's Discretion

- Exact Python module boundaries, adapter protocol types, schema field ordering,
  run-id generation, and CLI parser organization.
- Exact JSON Schema filenames and schema version suffixes, provided the canonical
  report/manifest/packet/fix-prompt artifacts and required fields exist.
- Whether the first local adapter invokes an installed agent command or uses the
  file-based packet flow as its execution boundary.
- The concrete stable fingerprint algorithm, provided it is deterministic and
  compatible with the existing resolution-ledger model.
- Concrete project-size limits and warning thresholds, provided full scope is
  available and limitations are reported.
- Automated versus user-confirmed resolution transitions when runtime evidence
  is unavailable.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Product and artifacts

- `docs/fresh-review-prd.md` — full product requirements, decisions, acceptance
  criteria, rollout, and non-goals.
- `docs/artifacts.md` — existing Quality Runner artifact paths, report contracts,
  resolution ledger, and read-only boundaries.
- `docs/cli.md` — existing CLI commands, shared flags, and gate/handoff flows.

### Existing implementation patterns

- `quality_runner/cli.py` — CLI dispatch and argument conventions.
- `quality_runner/artifacts.py` — run artifact creation and persistence.
- `quality_runner/schemas/` — versioned JSON Schema conventions.
- `quality_runner/code_quality_ledger.py` — finding fingerprint and ledger
  patterns.
- `quality_runner/fix_proposals.py` — read-only fixing-agent proposal behavior.
- `quality_runner/handoff_markdown.py` — human-readable agent handoff rendering.
- `quality_runner/mcp.py` — local MCP tool registration and payload patterns.

### Project rules

- `README.md` — local-first product positioning and v1 safety boundary.
- `AGENTS.md` — repository and implementation rules, when present.
- `.planning/PROJECT.md` — project scope, advisory-only constraint, and current
  phase direction.

</canonical_refs>

<specifics>
## Specific Ideas

- Top-level summary: `Review complete: X critical, Y high, Z medium issues found.`
- No-issue caveat: `No major issues found from available evidence, but this
  does not prove the feature works end-to-end.`
- Suggested artifact names: `review-manifest.json`, `review-context.json`,
  `review-report.json`, `review-report.md`, `review-agent-packet.md`, and
  `review-fix-prompts.md` under each run directory.
- Delivery sequence: schemas/artifacts; task review; blind/breadth/evidence;
  combined grouping; known issues/ledger; fixing prompts/loop; BYO adapter;
  real-task pilot.

</specifics>

<deferred>
## Deferred Ideas

- Team workflows, pull-request comments, hosted service, enterprise controls,
  automatic fixes/commits/PRs, deep security/compliance review, required visual
  testing, trend analytics, agent benchmarking, custom personas, multi-agent
  debate, CI enforcement, issue-tracker integration, release gates, automatic
  reproduction steps, and automatic stale known-issue expiration.

</deferred>

---

*Phase: 02-fresh-review*
*Context gathered: 2026-07-09 via PRD Express Path*
