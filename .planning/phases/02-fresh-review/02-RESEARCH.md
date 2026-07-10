# Phase 2: Fresh Review - Research

**Researched:** 2026-07-09
**Domain:** Python CLI, local artifacts, JSON Schema, MCP, and fresh-context agent handoff
**Confidence:** HIGH for repository architecture; MEDIUM for adapter details

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Fresh Review is local-first for solo developers using AI coding agents.
- Task-aware, blind, and combined modes are distinct; blind review receives no task or inherited reasoning.
- Reports are saved locally by default as Markdown and canonical JSON.
- Reviewers propose and hand off fixes but never edit source or execute remediation.
- Known issues remain visible, and active loops do not compare prior reports until end-of-cycle summarization.
- BYO-agent permissions remain owned by the selected agent adapter.

### Claude's Discretion

- Exact Python module boundaries, adapter protocol types, schema field ordering, run-id generation, and CLI parser organization.
- Exact JSON Schema filenames and schema version suffixes.
- The first local adapter’s process boundary versus file-based packet flow.
- Stable fingerprint algorithm compatible with the existing ledger.
- Project-size limits and warning thresholds.
- Automated versus user-confirmed resolution transitions without runtime evidence.

### Deferred Ideas (OUT OF SCOPE)

- Hosted service, team workflows, enterprise controls, automatic fixes/commits/PRs, CI enforcement, issue trackers, trend analytics, custom personas, multi-agent debate, and required visual testing.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FR-FRESH-CONTEXT | Every review pass uses a newly constructed mode-specific packet without inherited reasoning or active-cycle reports. | Existing manifests and read-only artifact boundaries provide the provenance pattern; a review manifest must record packet hashes and exclusions. |
| FR-REVIEW-MODES | Task, blind, and combined modes support task/project scope, breadth, exclusions, and evidence limitations. | `quality_runner/cli.py` uses subparser composition and `cli_workflow_args.py` centralizes shared flags. |
| FR-REPORTS | Reports contain ranked findings, evidence, confidence, uncertainty, suggested fixes, and agent prompts in JSON and Markdown. | Existing JSON/Markdown artifact pairs and `handoff_markdown.py` provide persistence and rendering patterns. |
| FR-STATE | Known issues and resolution state are local and cross-run matching is delayed during loops. | `code_quality_ledger.py` provides fingerprinted entries, accepted dispositions, and superseded states. |
| FR-BYO-AGENT | A local or file-based adapter can receive a fresh packet and return structured output or an explicit unavailable result. | Existing MCP tools use typed input schemas and structured result envelopes. |
| FR-SAFETY | The reviewer remains local-first and read-only. | `SECURITY.md`, `README.md`, `artifacts.py`, and existing symlink/run-id tests establish the boundary. |
</phase_requirements>

## Summary

Quality Runner is a Python 3.12+ package with a standard-library-heavy CLI and MCP surface. The CLI is assembled in `quality_runner/cli.py`, payload dispatch is centralized in `cli_payload.py`, artifacts are written below `.quality-runner/runs/<run-id>/`, and JSON schemas are packaged under `quality_runner/schemas/`. [VERIFIED: pyproject.toml, quality_runner/cli.py, quality_runner/cli_payload.py, quality_runner/artifacts.py]

The safest implementation is an additive review workflow that reuses the existing run directory and artifact writer but introduces review-specific schemas, context construction, normalized finding/report models, and a separate adapter boundary. Existing code-quality resolution logic reads the latest prior ledger, so active-loop freshness requires an explicit cycle-aware path that does not call prior-report matching until final summarization. [VERIFIED: quality_runner/code_quality_ledger.py]

**Primary recommendation:** Keep review logic in dedicated modules and compose it into CLI/MCP dispatch only after its contracts and read-only artifact tests exist. Reuse existing artifact path validation and ledger fingerprint concepts; do not overload `quality-audit.json` with task/blind review semantics.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CLI mode/scope parsing | CLI/application boundary | Review orchestration | Existing subparser and payload-dispatch pattern owns command behavior. |
| Fresh context construction | Review orchestration | Local repository reader | The review layer controls exactly which inputs enter a packet. |
| Agent invocation | BYO-agent adapter boundary | Review orchestration | The chosen agent owns execution and permissions; QR owns packet/result contracts. |
| Report normalization | Review domain | JSON/Markdown renderers | Findings need one canonical representation before two output formats. |
| Review persistence | Local filesystem/artifact layer | Resolution ledger | Existing safe artifact writer owns `.quality-runner` writes; review state is cycle-aware. |
| MCP exposure | MCP transport | Review orchestration | Existing JSON-RPC schemas and envelopes are the integration surface. |
| Read-only/path safety | Local filesystem boundary | Every adapter/output path | `SECURITY.md` and artifact helpers prohibit remote calls and unsafe writes. |

## Standard Stack

| Component | Version | Purpose | Evidence |
|-----------|---------|---------|----------|
| Python | >=3.12 | Runtime | Declared in `pyproject.toml`. [VERIFIED] |
| `argparse`, `json`, `pathlib` | Python stdlib | CLI, payloads, local artifacts | Used by existing CLI and artifact modules. [VERIFIED] |
| JSON Schema documents | Draft 2020-12 | Versioned artifact contracts | Existing schemas use `$schema`, `$id`, required fields, and const schema names. [VERIFIED: quality_runner/schemas/resolution-ledger.schema.json] |
| pytest, Ruff, basedpyright | Project tools | Verification | Commands and configuration are documented in `pyproject.toml` and `CONTRIBUTING.md`. [VERIFIED] |

No new runtime dependency is required by the repository evidence or the PRD. [VERIFIED: pyproject.toml]

## Architecture Patterns

### System Architecture Diagram

```text
CLI/MCP request -> options + repository snapshot + explicit evidence
                 -> mode-specific fresh packet
                 -> BYO-agent/file adapter
                 -> canonical report + fingerprints + cycle state
                 -> JSON + Markdown + fix prompts + end-of-cycle ledger
```

### Recommended Project Structure

```text
quality_runner/
  review.py                 # review orchestration and normalized findings
  review_context.py         # mode-specific packet construction and hashes
  review_adapters.py        # file/local adapter and result validation
  review_artifacts.py       # review payloads and Markdown rendering
  cli_review.py             # argparse and CLI payload integration
  schemas/review-*.schema.json
```

Exact names are discretionary, but freshness, normalization, adapters, CLI wiring, and artifact rendering should remain separately testable.

### Existing patterns to follow

1. Add a review subparser in the style of `run`, `inspect`, and `refresh`; route parsed arguments through `payload_for_args`. [VERIFIED: `quality_runner/cli.py`, `quality_runner/cli_payload.py`]
2. Build one normalized report payload, write it with `write_json`, and render Markdown from that payload. [VERIFIED: `quality_runner/artifacts.py`, `quality_runner/handoff_markdown.py`]
3. Validate the single-segment run id, reject symlinked artifact components, and write only below `.quality-runner/runs/<run-id>/`. [VERIFIED: `quality_runner/artifacts.py`, `tests/test_artifacts.py`, `SECURITY.md`]
4. Represent adapter success, unavailable capability, malformed output, and permission refusal explicitly; packet creation must not imply review completion. [VERIFIED by existing typed MCP input/result patterns: `quality_runner/mcp.py`]

### Anti-Patterns to Avoid

- Passing implementation-agent transcripts, prior reports, or combined findings into a fresh reviewer by default.
- Calling the prior-run ledger lookup during an active loop.
- Writing Markdown independently from JSON.
- Treating a fixing-agent prompt as permission for QR to edit source.
- Accepting an unvalidated agent response as a completed review.
- Persisting sensitive task/evidence content outside the local report boundary.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Run directory safety | A second path validator | `artifact_dir` / `prepare_artifact_dir` | Existing tests cover traversal and symlink cases. |
| Finding identity | Ad hoc report titles | Existing fingerprint/ledger conventions | Stable identity is required for resolution state. |
| Report serialization | Separate Markdown data model | Render from canonical JSON | Prevents tool/human output drift. |
| MCP transport | A new JSON-RPC server | Existing `mcp.py` list/call/response patterns | Preserves packaged tool behavior. |

## Common Pitfalls

### Freshness leakage

**What goes wrong:** A context builder includes a previous summary, prior report, or combined result in the reviewer packet. **Prevention:** Build a mode allowlist, hash included inputs, and test blind packets for absence of task text and active-cycle report ids. **Warning signs:** Blind findings use “missed requirement” language or a packet contains a prior report path.

### False completion without an adapter

**What goes wrong:** A packet is saved and the command says review complete although no agent ran. **Prevention:** Separate `packet-created` from `review-complete`; require validated structured output. **Warning signs:** Empty findings with no adapter/provenance.

### Ledger contamination during loops

**What goes wrong:** The reviewer sees prior findings before the fixing cycle completes. **Prevention:** Pass cycle id and `allow_prior_matching=false` to active review paths; only the final summarizer matches prior fingerprints. **Warning signs:** Active reports contain “resolved from previous run” labels.

### Unsafe or noisy reports

**What goes wrong:** Sensitive evidence is persisted without redaction, or full breadth creates unranked low-confidence noise. **Prevention:** Apply exclusions/redaction before writes, enforce configured limits, and report omitted paths and evidence gaps.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | No | No QR-owned login boundary. |
| V3 Session Management | No | Do not persist hidden agent session state. |
| V4 Access Control | Yes | Enforce repo-root and artifact-root boundaries; never expand adapter access silently. |
| V5 Input Validation | Yes | Validate CLI paths, run ids, adapter payloads, enums, and report shape. |
| V6 Cryptography | Limited | Use standard-library hashes for provenance/fingerprints; never use hidden reasoning as identity data. |

### STRIDE Threat Register

| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| Malicious run id or symlinked artifact path | Tampering/Elevation | Reuse existing validation and symlink rejection; add review artifact tests. |
| Agent output claims success or writes arbitrary files | Spoofing/Tampering | Validate adapter output and write only QR-owned paths. |
| Sensitive task/evidence leaks into reports | Information disclosure | Apply exclusions/redaction before persistence and record only metadata. |
| Full-project traversal overwhelms process | Denial of service | Enforce breadth/size limits and explicit incomplete-review status. |
| Adapter silently exfiltrates code | Information disclosure | Core remains local-only; adapters are explicit, user-selected, and expose access state. |

## Open Questions (RESOLVED)

1. **Artifact location?** — RESOLVED: existing `.quality-runner/runs/<run-id>/` with review-specific filenames.
2. **Active-loop bias?** — RESOLVED: no prior review documents in active packets; matching only in final summarization.
3. **No adapter?** — RESOLVED: write a validated packet, report `review-not-run`, and never claim completion.
4. **New runtime dependency?** — RESOLVED: none required; use stdlib and existing QR modules unless implementation evidence proves otherwise.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | CLI/tests | Yes | Project requires >=3.12 | None; required runtime. |
| pytest | Repository tests | Project-configured | Not pinned in `pyproject.toml` | Use documented `python3.14 -m pytest -q`. |
| BYO coding agent | Actual review execution | Adapter-dependent | Not owned by QR | File-based packet flow reports `review-not-run` when absent. |

**Missing dependencies with no fallback:** None for artifact and contract work.

**Missing dependencies with fallback:** Agent execution has the explicit file-based packet fallback.

## Sources

### Primary (HIGH confidence)

- `docs/fresh-review-prd.md` — product requirements and acceptance criteria.
- `docs/artifacts.md`, `docs/cli.md`, `README.md`, `SECURITY.md` — artifact, CLI, local-only, and read-only boundaries.
- `pyproject.toml`, `quality_runner/cli.py`, `quality_runner/cli_payload.py`, `quality_runner/artifacts.py`, `quality_runner/code_quality_ledger.py`, `quality_runner/mcp.py`, `quality_runner/handoff_markdown.py` — verified implementation patterns.
- `tests/test_artifacts.py`, `tests/test_mcp.py` — verified safety and MCP test patterns.

### Secondary (MEDIUM confidence)

- None needed; this phase uses existing repository conventions and no external framework claim.

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:** Standard stack HIGH; architecture HIGH; adapter details MEDIUM because the PRD intentionally leaves the first adapter boundary to implementation planning.

**Research date:** 2026-07-09
**Valid until:** 2026-08-08 for repository architecture; revisit if CLI/MCP contracts change.
