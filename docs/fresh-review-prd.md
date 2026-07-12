# Fresh Review PRD

## 1. Product definition

Fresh Review is a local-first Quality Runner workflow that gives a completed
AI-agent task a skeptical second pass. Each review is run by a newly invoked
review context with only the inputs declared by the selected mode. The reviewer
reports evidence-backed defects, credible suspicions, project risks, and missing
evidence; it does not edit source files or execute fixes.

The first audience is solo developers using AI coding agents. The first release
is a CLI/MCP-adjacent extension of Quality Runner, not a new hosted service or
agent provider.

## 2. Goals and non-goals

### Goals

- Catch missed requirements, unwired or inaccessible behavior, inconsistent
  project patterns, regression risks, and misunderstood intent after agent work.
- Make uncertainty explicit while still allowing aggressive, useful suspicion.
- Produce a ranked report that a human can act on and a separate fixing agent can
  consume with minimal rewriting.
- Preserve a genuinely fresh review context on every pass.
- Save review history, known issues, and end-of-cycle resolution state locally.

### Non-goals for v1

- Reviewer-driven source edits, dependency installation, commits, pull requests,
  or automatic remediation.
- Hosted/cloud review, team approvals, enterprise permissions, or a new model
  provider.
- Guaranteed end-to-end correctness without runtime or application evidence.
- Required browser/computer automation, production-data inspection, or formal
  security/compliance certification.
- CI enforcement, issue-tracker integration, trend analytics, or multi-agent
  debate.

## 3. User-facing workflow

The primary command is:

```text
quality-runner review <repo-root> [options]
```

Recommended initial options:

```text
--mode task|blind|combined       default: task
--scope task|project            default: task for task mode, project for blind
--breadth focused|related|full  default: related for project scope
--task TEXT
--task-file PATH
--reuse-task [TASK-ID]
--previous-summary PATH         opt-in only
--exclude CATEGORY|PATH         repeatable
--evidence PATH                 repeatable, local files only
--detail concise|standard|full  default: standard
--save / --no-save              default: save
--known-issues accept|edit|remove|skip
--loop-stop critical-high|none  loop mode only
--loop                         manually start an implement-review cycle
--finding-id ID                 repeatable fixing-agent selection
--all-critical-high             handoff shortcut
--json
```

The command must fail clearly, rather than infer task satisfaction, when task
mode has no task. It should offer blind review as the alternative. A missing
diff does not prevent a project review; it lowers confidence and is reported.

The default normal flow is task-aware fresh adversarial review. Blind and
combined modes are explicit alternatives. Project breadth `related` covers
changed areas plus nearby routing/navigation, access paths, data flow, and
matching project patterns. `focused` limits inspection to the changed area and
direct dependencies; `full` scans the project subject to configured exclusions
and practical size limits.

## 4. Freshness contract

Freshness is a context-packaging guarantee, not a claim about a model’s hidden
memory. Every review pass receives a newly constructed input packet and a new
agent invocation/session. The packet is recorded in the run manifest by hashes
and provenance, not by duplicating sensitive content unnecessarily.

### Task mode input

- Original task text, from `--task`, `--task-file`, or a saved task.
- Current repository snapshot and git state.
- Changed files and diff metadata when available.
- Selected scope, breadth, exclusions, and evidence.
- Known issues only after the normal-run verification step.

### Blind mode input

- Current repository snapshot and git state.
- Changed files and diff metadata when available.
- Selected scope, breadth, exclusions, and evidence.
- No original task, previous agent conversation, previous reasoning, self-review,
  or prior review report.

### Optional context

The previous implementation agent’s summary is excluded by default and may be
included only through `--previous-summary`. Prior review documents are never
provided to a reviewer during an active implement-review cycle. They may be
used only by the end-of-cycle summarizer to correlate findings and statuses.

Combined mode runs task and blind packets independently, then performs a local
post-processing pass to group related findings. One review’s findings are not
fed into the other review.

## 5. Agent boundary and BYO-agent integration

Quality Runner owns orchestration, context packaging, artifact validation, and
local persistence. The user’s selected agent owns model execution and its own
permission/allowance prompts. The product must not silently transmit project
content to a remote service.

The adapter contract should support at least:

1. Create a fresh invocation with a rendered review packet.
2. Return structured JSON when available, plus raw agent output for auditability.
3. Request optional evidence access through the agent’s native permission flow.
4. Report unavailable capabilities without converting them into false findings.

The first implementation may support one local adapter plus a file-based adapter
for any agent: write a review packet and read a returned report. Agent-specific
permission breadth, browser automation, and logged-in application access remain
adapter concerns. Quality Runner must not implement a universal permission model.

If no agent adapter is available, the command still produces a validated,
shareable packet and explains how to run it manually; it must not claim that a
review occurred.

## 6. Review report

Each completed review writes both human-readable Markdown and agent-friendly
JSON. A `review-complete` report with findings uses this top line:

```text
Review complete: X critical, Y high, Z medium issues found.
```

A `review-not-run` result begins `Review packet ready:` and tells the user to
send the packet to a reviewer. Other incomplete adapter states begin `Review
did not complete`; neither outcome may imply a finding conclusion.

The report records mode, scope, breadth, reviewer adapter, repository state,
task provenance (or explicit blind omission), exclusions, evidence used,
evidence unavailable, and freshness metadata.

Required sections, in this order:

1. Executive summary and severity counts.
2. Missed requirements (task/combined only; present even when empty).
3. Confirmed issues.
4. Suspected issues.
5. Not enough evidence.
6. Project consistency risks.
7. Regression risks.
8. Known accepted issues.
9. Suggested fixes.
10. Agent handoff prompts.
11. Remaining uncertainty and unreviewed areas.

Each finding contains:

- Stable finding id and fingerprint.
- Severity: `critical`, `high`, `medium`, or `low`.
- Classification: `confirmed`, `suspected`, `not-enough-evidence`, or
  `known-accepted`.
- What seems wrong and why it matters.
- Evidence and where to look (files, symbols, routes, commands, or artifacts).
- Recommended human fix.
- Fixing-agent prompt that asks the agent to investigate, stay in scope, fix
  only with approval, and verify the result without prescribing uncertain code.
- Confidence: `high`, `medium`, or `low`.
- Whether human confirmation is required.
- Current status.

Confidence describes evidentiary support; severity describes potential impact.
They must remain independent. A high-severity, low-confidence suspicion is
allowed, but must not be presented as a confirmed defect.

When no issues are reported, the report must say:

```text
No major issues found from available evidence, but this does not prove the
feature works end-to-end.
```

## 7. Artifact contract

Review artifacts extend the existing run directory:

```text
.quality-runner/runs/<run-id>/
  review-manifest.json
  review-context.json
  review-report.json
  review-report.md
  review-agent-packet.md
  review-fix-prompts.md
```

Combined runs additionally contain separate task and blind result payloads
before final grouping. The exact filenames may be versioned with the schema, but
the human report, machine report, packet, and fix prompts must remain separately
available.

`review-manifest.json` records run id, schema version, timestamps, git HEAD and
dirty state, mode, scope, breadth, exclusions, evidence references, adapter,
freshness policy, and hashes of context inputs. It must not include hidden model
reasoning.

`review-report.json` is the canonical machine-readable contract. Markdown is a
rendering of the same normalized findings, not a second source of truth.

Reports are saved by default under `.quality-runner/runs/<run-id>/`. A no-save
option may suppress report persistence, but the command must still state that no
shareable report was written.

## 8. Status, known issues, and resolution tracking

Use simple human-facing statuses in v1:

- `open`
- `resolved`
- `accepted`
- `needs-confirmation`
- `not-enough-evidence`

The machine report may retain richer transition metadata such as proposed-fix
sent and likely-resolved, but those are not required user decisions.

Known issues are stored in a project-level local file, preferably alongside
existing Quality Runner state (for example `.quality-runner/known-issues.json`).
Before a normal review, the CLI presents the list and allows accept, edit, or
remove. During an active loop, it does not interrupt for this step. A repeated
known issue remains visible and is marked previously accepted.

For v1, “major project change” means any of:

- the repository’s default branch or configured baseline changes;
- a review changes files outside the prior review’s in-scope paths;
- a configured high-risk path changes (routing, auth/permissions, data schema,
  migrations, or deployment configuration); or
- the user explicitly requests re-verification.

This deterministic rule is preferable to an opaque change-size score. On the
next normal run after a major change, known issues are presented for
re-verification before the review starts.

Finding resolution is tracked in the existing resolution-ledger concept, using
review fingerprints and cycle ids. Matching against prior reports is disabled
while a cycle is active. At cycle completion, a summarizer may classify findings
as open, resolved, accepted, superseded, or uncertain; automatic resolution is
never final without evidence, and user confirmation controls `resolved` when the
review cannot verify behavior.

## 9. Implement-review loop

The loop is explicitly started by the user with `--loop`. Each iteration is:

1. Run a fresh review.
2. Save the current report and show ranked findings.
3. Hand selected findings, or the critical/high shortcut, to a separate fixing
   agent through `review-fix-prompts.md`.
4. Wait for the fixing agent to report completion.
5. Start a new fresh review without prior review context.
6. Stop when the selected condition is met or the user stops manually.

Supported stop conditions are `critical-high` (no critical/high findings) and
`none` (no findings). Medium/low findings do not block the first condition but
remain in the cycle summary. Known-issue verification is deferred until the
cycle ends. The final cycle summary is the first place where cross-run finding
matching is allowed.

## 10. Evidence and privacy

Applicable evidence includes repository files, diffs, project intent files,
screenshots, test output, app behavior notes, and capabilities exposed by the
selected agent. Evidence is opt-in when it requires access beyond local files.
The report must distinguish evidence that was unavailable from evidence that
was checked and found negative.

Reports may contain sensitive source paths, snippets, screenshots, logs, and
task text. V1 remains local-first and must not call remote services from core
Quality Runner. V1 should support path exclusions and a configurable redact
list before a report is persisted or handed to an agent. A future security or
privacy review is required before broad use on sensitive or regulated projects.

## 11. Acceptance criteria

- Task mode evaluates task satisfaction without receiving the implementation
  agent’s conversation or reasoning by default.
- Blind mode cannot receive the original task and does not call findings
  missed requirements.
- Combined mode produces independent task and blind results and only groups
  overlaps after both complete.
- Every run records its freshness policy and input provenance.
- Reviewers never edit source files, install dependencies, commit, or execute
  remediation.
- Reports contain all required sections, severity counts, confidence, evidence
  limitations, human fixes, and agent prompts.
- No-issue reports include the end-to-end caveat.
- Reports are saved locally by default in the existing run artifact area.
- Known issues are visible, editable, and never silently hidden.
- Active loops do not compare prior review reports until final summarization.
- Fixing-agent handoff is separate from reviewing and is limited to selected
  findings or the explicit critical/high shortcut.
- The CLI reports adapter or evidence-access limitations without fabricating
  review results.

## 12. Delivery sequence

1. Define and validate review schemas, context manifests, and artifact paths.
2. Implement task-mode fresh packet and report normalization.
3. Add blind mode, breadth controls, exclusions, and evidence references.
4. Add combined mode and local post-review grouping.
5. Add known issues and resolution-ledger integration.
6. Add fix-prompt handoff and manual loop orchestration.
7. Add the first BYO-agent adapter and file-based fallback.
8. Pilot on real completed AI-agent tasks; measure useful findings, noise,
   prompt usability, freshness leaks, and sensitive-report exposure.

## 13. Decisions still requiring client confirmation

The integrator recommends these defaults but does not mark them as client
decisions:

- Keep the simple statuses: Open, Resolved, Accepted, Needs confirmation, and
  Not enough evidence.
- Default fixing-agent handoff to user-selected findings, with an explicit
  all-critical/high shortcut.
- Ship the core review command first; ship the loop in the same release only
  if adapter orchestration remains small and reliable.
- Treat the pilot threshold as continued use before trusting or merging agent
  work, with at least one meaningful missed issue found in repeated usage.
- Use the deterministic major-change rule in section 8 for known-issue
  re-verification.
