# Pronto behavior assurance

Quality Runner validates repository-owned behavior contracts and immutable
receipts. It does not infer passing behavior from source, test names,
documentation, or mutable checklists.

## Repository contract

The contract lives at .pronto/behavior-assurance.json. Quality Runner reads
pronto-behavior-assurance/v1 and pronto-behavior-assurance/v2. Version 1 remains
valid but projects as legacy and edge-unprofiled. Version 2 adds non-empty
behavior invariants and optional scenario edge profiles:

    {
      "schema": "pronto-behavior-assurance/v2",
      "applicability": "applicable",
      "approved_producers": ["quality-runner"],
      "behaviors": [{
        "id": "save-state",
        "title": "State survives reload",
        "tier": 0,
        "automation": "on_demand",
        "change_triggers": ["src/state/**", "src/storage/**"],
        "invariants": ["A successful save survives reload."],
        "scenarios": [{
          "id": "reload-restores-value",
          "title": "Reload restores a saved value",
          "oracle": "After saving and reloading, the same value is visible.",
          "verification_level": "automated",
          "edge_profile": {
            "categories": ["state_and_ordering"],
            "risk": "routine",
            "side_effects": "reversible"
          }
        }]
      }]
    }

For a newly created, cloned, attached, or registered repository, the fleet
onboarding matrix makes the v2 contract and complete edge_profile metadata on
every scenario a baseline requirement. The optional-profile behavior remains
for existing-fleet migration and audit: those repositories stay visibly
unprofiled or partially profiled until their source contract is repaired.

Tier 0 is release-blocking. Tiers 1 and 2 remain auditable inventory and do not
gate release. A separate coverage projection evaluates every scenario and
reports total, profiled, verified, stale, failed, blocked, and unknown counts
per tier and declared edge category.

The eight categories are input_and_encoding, state_and_ordering,
repetition_and_idempotency, timing_and_concurrency,
interruption_and_recovery, resource_pressure, authorization_and_session, and
environment_and_cross_surface. Risk is routine or hostile; side effects are
none, reversible, or destructive.

A repository without applicable runtime behavior may declare not_applicable
only with a non-empty reason and no behaviors. Missing and invalid contracts
remain visible gaps.

## Immutable receipts

Receipts live under .quality-runner/behavior-assurance/receipts and use schema
quality-runner-behavior-receipt/v1. They identify the contract digest, versioned
producer, generation time, exact branch and commit, and scenario results.

For source or automated scenarios, use the bounded producer:

    qr behavior verify --behavior-id save-state \
      --scenario-id reload-restores-value \
      --timeout-seconds 120 \
      /path/to/repo \
      -- pnpm test -- --runInBand

The producer requires a committed contract, refuses dirty trigger paths,
executes argv without a shell, and records bounded output hashes. It cannot
claim direct-surface or independent verification.

For a bounded direct-surface edge session:

    qr behavior record-edge \
      --repo /path/to/repo \
      --behavior save-state \
      --scenario reload-restores-value \
      --environment local \
      --surface cli \
      --status passed \
      --trace /tmp/edge-trace.json \
      --json

record-edge accepts only local, test, preview, or staging targets and never
issues independent evidence. It rejects destructive profiles, dirty trigger
paths, oversized or malformed traces, and failed traces that were not replayed
and minimized. Security-sensitive raw traces stay in Quality Runner's private
local store; repository receipts expose only sanitized reproduction metadata
and hashes.

Receipt IDs are content-addressed. Removing receipt_id and hashing the canonical
remaining object produces receipt-<first-24-digest-characters>. Editing a
receipt invalidates its identity instead of rewriting history.

A receipt may carry forward from an ancestor only while its contract digest
matches and no committed, dirty, or untracked path since that commit matches the
behavior's change triggers. Open or expired defects block their scenarios.

## Fleet projection

Every repository projection contains separate applicability, contract, result,
freshness, release, coverage, defect, and gap evidence. Release readiness still
depends only on current trusted Tier-0 receipts or a valid explicit
not-applicable contract. Missing, malformed, failed, blocked, stale,
target-mismatched, or insufficient evidence never becomes green. The projection
also carries an explicit routing state: missing_contract, legacy_v1, unprofiled,
partially_verified, stale, failed, blocked, unknown, current, or not_applicable.
This summary never replaces the dimensional fields.

Use the immutable fleet flow to publish the result:

    qr fleet audit run --all --projects-root /path/to/projects --json
    qr fleet audit replay --audit-id AUDIT_ID --json
    qr fleet audit feed --audit-id AUDIT_ID --json

The first adoption audit is expected to report gaps. Add contracts before
receipts and let change triggers reduce future reruns rather than weakening the
initial bar.
