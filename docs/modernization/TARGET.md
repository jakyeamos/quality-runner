# Modernization Target

## Product promise

Quality Runner should make one trustworthy statement after every operation:

> Here is what was inspected or executed, what confidence the evidence supports,
> what was written, and the single safest next action.

It remains a local-first CLI/MCP tool. The modernization is a command and
artifact experience redesign, not a browser dashboard project.

## Product principles

- **Truth before optimism.** “No review ran,” “verification was blocked,” and
  “evidence is incomplete” are first-class outcomes, never empty success states.
- **Safety is visible.** Scan-only, in-place verification, and isolated
  verification have distinct names, explicit consent, and clear output.
- **One user job at a time.** Common flows start from audit, review, verify, or
  run history; implementation concerns stay behind those concepts.
- **Artifacts support decisions.** JSON remains canonical and Markdown remains
  readable, but both lead with outcome and next action rather than a path dump.
- **Compatibility earns its place.** Existing public surfaces stay available
  through a versioned transition, but new development leads with one modern API.

## Interaction direction

The default interaction is a compact, plain-text outcome card followed by a
next-step command or artifact reference. Progressive help introduces advanced
policy, controller, and validation operations only when needed. Existing command
names can remain as deprecated aliases while the preferred surface groups work
by journey: audit, review, verify, and runs.

Fresh Review has two intentionally different successful outcomes: a completed
review with findings/confidence, or a prepared packet awaiting a reviewer. The
latter is never summarized as a clean review. Markdown and JSON preserve that
distinction for humans, agents, and MCP clients alike.

## Architecture

The target has a strict inward dependency direction:

```text
CLI / MCP / compatibility adapters
            ↓
application use cases and outcome rendering
            ↓
typed domain contracts and pure analysis pipeline
            ↓
artifact, filesystem, git/worktree, and process infrastructure
```

- **Domain contracts** name evidence, findings, run state, review state, and
  execution policy. They use standard-library dataclasses, TypedDicts, and
  protocols where appropriate; serializers own JSON compatibility.
- **Application use cases** own inspect, plan, verify, review, and release
  outcomes. They do not parse CLI flags or write arbitrary JSON directly.
- **Infrastructure** owns safe artifact resolution, atomic persistence, bounded
  repository walking, subprocess isolation, and Git worktrees.
- **Adapters** translate CLI arguments, MCP requests, and legacy package calls
  to the use cases. They hold presentation and backward-compatibility logic,
  not domain decisions.

This solves the repeated workflow setup, `dict[str, Any]` handoffs, and adapter
import cycle without changing the semantic meaning of established artifacts.

## Safety and state model

Run artifacts are immutable evidence once finalized. Mutable controller state
uses atomic replace and a lock/compare strategy so concurrent agents cannot
silently lose responses. Every artifact path is validated for containment and
symlink safety before reading or writing.

Verification is an effectful service, not part of scanning. Unknown discovered
commands are non-executable by default. An explicit verification request runs
in a disposable checkout with a minimal inherited environment. That checkout
protects the source worktree from normal mutations; it is not a sandbox for
arbitrary local commands. No core flow sends repository content to a remote
service.

## Public contracts and migration

V1 JSON schemas, artifact locations, console scripts, MCP tools, and extracted
compatibility packages remain readable and callable during the migration. V2
adds versioned serializers and an adapter layer rather than silently altering a
stored artifact. New clients use the v2 outcome model; legacy clients receive
the v1 projection until the published deprecation window ends.

The package version has one source of truth. Release checks compare that value
with built distribution metadata, runtime CLI/MCP values, plugin metadata, and
documented install surfaces.

## Quality strategy

The test portfolio is organized around contracts and risks:

- golden CLI/MCP/artifact fixtures before each migrated vertical slice;
- traversal, symlink, subprocess-policy, and interruption tests for safety;
- property or table-driven tests for serializers and run-state transitions;
- focused unit tests for pure analyzers plus end-to-end fixtures for each user
  journey;
- release tests that install the built wheel and exercise every public script;
- a committed, locked developer toolchain and CI checks that make coverage and
  formatting claims real.

## Dependencies and non-goals

The first modernization milestones use the standard library rather than adding
a framework merely to model data or run a CLI. A new dependency is acceptable
only when an evaluated need—such as cross-platform process isolation—cannot be
met safely with the existing platform assumptions.

The target does not introduce a hosted service, autonomous remediation, a broad
web application, silent agent execution, or a breaking removal of the legacy
packages. An optional TUI is a post-cutover product decision, not a prerequisite
for clarity.
