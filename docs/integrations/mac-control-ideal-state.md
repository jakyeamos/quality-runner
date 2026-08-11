# Mac Control ideal-state audit

Quality Runner owns the bounded fleet audit for the additional Mac Control
ideal-state gate. The audit is deliberately separate from the numeric
`0–4` maturity feed: it produces a companion report for Pronto and never
changes `maturity.json`.

## Repository contract

An applicable repository owns this file:

```text
.mac-control/ideal-state.json
```

The current manifest uses `mac-control-task-manifest/v4`; v1 through v3 remain
readable migration formats. V4 replaces self-attested `criteria` booleans with
task-level `semantic_evidence`. The repository must leave `criteria` absent or
empty. Quality Runner derives all eight results only after it resolves every
declared repository-relative source reference and finds its anchor and evidence
tokens near one unique anchor in a regular UTF-8 implementation source file
under the audited repository root. Docs, tests, fixtures, snapshots, symlinks,
path traversal, oversized files, and unsupported source extensions cannot score.

Each task declares a `surface_kind` and criterion-specific claims for stable
identity, correct semantics, observable state, useful hierarchy, efficient
navigation, verifiable outcomes, route flexibility, and stable behavior across
change states. Claims are typed: identity requires a unique stable selector;
verification requires an operator and non-generic expected value; route
evidence identifies distinct primary and secondary providers plus the task's
fallback policy; and change
evidence accounts for enabled, disabled, loading, and permission-unavailable
states with a typed failure behavior. Navigation strategy, direct entry point,
readback provider, expected state, selector identity, and fallback policy must
also agree with the task's independent fields. Copying one evidence object
across dimensions is invalid.

The surface kind also constrains providers. Native app UI requires a native
semantic route, web content requires a browser connector rather than native
Accessibility, and a hybrid transition must declare both sides. Visual,
pointer, and drag candidates require a fresh-state handoff. Accessibility
routes require a stable accessibility identifier.

`selected_route` is forbidden in a v2, v3, or v4 repository manifest. It is live evidence
produced after Mac Control measures an eligible candidate for the current
app/task context. A sequential keyboard route, Accessibility scroll route,
shortcut, or visual/pointer route may be declared when the task genuinely
supports it, but none receives static preference. Visual fallback is not
required for scoring, and search tasks are not required to implement a
universal Command-K shortcut.

A repository without a supported task surface must still own a manifest with
`applicability: "not_applicable"` and a current reason. A missing manifest is
reported as missing contract evidence, not as not-applicable.

## Evidence lanes

Static QR validation is bounded and read-only. It checks the manifest for every
discovered repository and writes immutable artifacts under the runtime-owned
Mac Control audit directory. It does not infer a live GUI result.

The audit reports two independent lanes:

- Implementation contract: the v4 manifest is structurally valid and all eight
  semantic dimensions are grounded in live source files for every supported
  task. Human accessibility, agent task operability, and source grounding remain
  distinct evidence even while the v1 report envelope carries them in one
  implementation lane. This lane does not prove runtime task success or that a
  packaged app is running.
- Live task evidence: supported tasks have attempts, readable postconditions,
  successful receipts, and route evidence from the running app or an approved
  evidence producer. An unattempted task is review_required; an attempted task
  with a failed postcondition is failed.

The report exposes these as implementation_contract.status and
live_task_evidence.status. A valid manifest can therefore be
implementation passed while live task evidence is review_required. The
combined audit remains review_required until both lanes pass.

Only the current v4 manifest can earn implementation points, and each point is
derived from source grounding rather than a repository boolean. V1 through v3
remain readable declaration-only formats. Their true booleans are retained as
`declaration_criteria_count` for explanation, but they contribute `0/8` and are
reported as `review_required` until migrated to v4. A structurally valid v4
manifest with only seven grounded dimensions reports `7/8` with the exact
missing anchor, token, file, or claim in `dimension_states` and
`grounding_errors`.

Measured task evidence is supplied through redacted sidecars named by stable
repository ID:

```text
<evidence-dir>/<repo-id>.json
```

The current sidecar uses `mac-control-task-evidence/v2`. V1 remains readable
for migration diagnostics but cannot satisfy live measurement. V2 binds the
producer identity, repository commit, and a digest of the manifest plus every
implementation source referenced by v4. Each task carries structured attempts,
not caller-supplied aggregate counts. Every attempt must identify one declared
route candidate, a digest-bound receipt whose provider and method match that
route, and an independent postcondition readback that agrees with the task's
oracle and `verifiable_outcomes` claim. QR derives attempts and successes from
those records; free-form evidence strings cannot make a task measured.

QR also records whether any manifest or referenced source path is dirty. A
dirty or unverifiable relevant worktree remains review-required instead of
being attributed to the current Git commit. Route ranking and latency belong
to Mac Control and this live evidence lane, not to repository remediation.

The optional live lane is explicit:

```bash
qr fleet mac-control audit run --all --projects-root /path/to/projects \
  --live --evidence-dir /path/to/mac-control-evidence --json
```

This invokes `macctl ideal-state audit` for applicable manifests and persists
only redacted structural result metadata. Task execution remains bounded by
Mac Control's own approval and receipt contracts; the QR gate passes only
when measured task evidence is also present.

## Publication and Pronto scope

Replay first, then publish the companion report:

```bash
qr fleet mac-control audit replay --audit-id AUDIT_ID --json
qr fleet mac-control audit feed --audit-id AUDIT_ID --json
```

The published path is:

```text
~/.quality-runner/fleet-audit/current/mac-control-ideal-state.json
```

The report declares `scope: "quality_runner_fleet"`, so it may contain a
larger discovered fleet. Pronto evaluates only its current maturity-applicable
repository subset and still blocks when any current repository is absent,
unknown, stale, invalid, or not commit-matched.
