# Mac Control ideal-state audit

Quality Runner owns the bounded fleet audit for the additional Mac Control
ideal-state gate. The Mac Control lane remains distinct from the numeric
`0–4` maturity score, but the normal QR fleet audit runs both lanes under one
freshness boundary and publishes a coordinated checkpoint. Mac Control does
not change the QR score; it contributes a separately displayed gate and
quality status inside the checkpoint.

## Repository contract

An applicable repository owns this file:

```text
.mac-control/ideal-state.json
```

The manifest uses `mac-control-task-manifest/v1` and describes the supported
application and tasks. Each task must declare a stable target, meaningful
hierarchy, direct semantic action, readable postcondition, all observable
states, explicit loading/modal/disabled/permission-unavailable states, an
efficient navigation strategy, and eligible plus selected routes. Routes are
`native_api`, `adapter`, `accessibility`, `keyboard`, `scrolling`, and the
explicitly approved `visual_fallback_approved`.

A repository without a supported task surface must still own a manifest with
`applicability: "not_applicable"` and a current reason. A missing manifest is
`unknown`, not not-applicable.

## Evidence lanes

Static QR validation is bounded and read-only. It checks the manifest for every
discovered repository and writes immutable artifacts under the runtime-owned
Mac Control audit directory. It does not infer a live GUI result.

The audit reports two independent lanes:

- Implementation contract: the repository manifest, eight criteria, task
  structure, semantic routes, observable states, change states, and static
  evidence references are present and structurally valid. Source or test
  references may support this lane when supplied, but this lane does not prove
  that a packaged app is running.
- Live task evidence: supported tasks have attempts, readable postconditions,
  successful receipts, and route evidence from the running app or an approved
  evidence producer. An unattempted task is review_required; an attempted task
  with a failed postcondition is failed.

The report exposes these as implementation_contract.status and
live_task_evidence.status. A valid manifest can therefore be
implementation passed while live task evidence is review_required. The
combined audit remains review_required until both lanes pass.

Measured task evidence is supplied through redacted sidecars named by stable
repository ID:

```text
<evidence-dir>/<repo-id>.json
```

The sidecar uses `mac-control-task-evidence/v1` and records the observed
commit, criteria evidence, task attempts, successful postconditions, selected
route, and evidence references. QR verifies the sidecar identity against its
own discovered repository commit.

The optional live lane is explicit. To include it in the same QR checkpoint:

```bash
qr fleet audit run --all --projects-root /path/to/projects \
  --mac-control-live --macctl macctl --json
```

The lower-level lane command remains available for targeted or compatibility
audits:

```bash
qr fleet mac-control audit run --all --projects-root /path/to/projects \
  --live --evidence-dir /path/to/mac-control-evidence --json
```

This invokes `macctl ideal-state audit` for applicable manifests and persists
only redacted structural result metadata. Task execution remains bounded by
Mac Control's own approval and receipt contracts; the QR gate passes only
when measured task evidence is also present.

## Publication and Pronto scope

For the normal flow, replay and publish the containing QR audit. This creates
the Mac Control report and the coordinated checkpoint together:

```bash
qr fleet audit replay --audit-id AUDIT_ID --json
qr fleet audit feed --audit-id AUDIT_ID --json
```

The coordination pointer is:

```text
~/.quality-runner/fleet-audit/current/maturity-checkpoint.json
```

It uses `quality-runner-maturity-checkpoint/v1` and binds both audit IDs, one
`as_of`, one repository population, and matching canonical target commits.
When QR has an exact target checkout, the Mac Control lane audits that same
checkout, including when the target status is stale or blocked; the QR inventory continues to retain the repository's original
primary path and custody evidence separately.
Publication fails closed if either replay or any binding check fails. The
existing sidecars are still written for older consumers, but new consumers
must use the pointer and its hashed versioned bundle.

For a standalone Mac Control audit, replay first, then publish the companion
report:

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
