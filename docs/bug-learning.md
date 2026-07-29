# Bug-learning lifecycle

Quality Runner separates immediate repository protection from reusable rule
promotion:

```text
repository regression
  -> reusable candidate
  -> Quality Runner advisory
  -> fleet observation
  -> required gate
```

Every confirmed bug belongs in a repository-owned
`quality-runner-candidates.json`. That does not make it a scanner rule. The
registry must connect every declared regression to one candidate and either
advance it through the governed lifecycle or record `repository-only`,
`duplicate`, or `not-detectable`. Missing coverage and skipped transitions are
validation failures.

## Candidate registry

The `quality-runner-candidate-registry-v0.1` contract records:

- the originating regression test, command, confirmation time, and provenance;
- the broader failure pattern and cause;
- producer and consumer surfaces;
- the proposed detection signal and likely false positives;
- concrete remediation and owner;
- deterministic positive and negative fixture paths;
- classified observation evidence, duration, and provenance;
- append-only transitions with actor, reason, timestamp, and evidence;
- an explicit terminal disposition when the lesson should not become a rule.

Validate the workflow without modifying the repository:

```bash
qr candidates validate /path/to/repo --json
```

This check only knows the confirmed regressions declared in the registry.
Teams should add the registry update to the originating bug-fix definition of
done. The regression test protects that repository immediately even when the
candidate remains advisory or receives a terminal disposition.

## Fleet observation

Aggregate candidate registries under a bounded projects root:

```bash
qr candidates aggregate \
  --projects-root /path/to/projects \
  --output /private/path/candidate-fleet.json \
  --as-of 2026-07-29T12:00:00Z \
  --json
```

The private `quality-runner-candidate-fleet-v0.1` artifact groups the same
candidate ID across independent repository identities. Re-running against the
same output path merges earlier observations by provenance, so an occurrence
does not disappear merely because a repository later rotates local evidence.
Invalid registries block the aggregate instead of being silently omitted.

Each observation is human-classified as `true-positive`, `true-negative`,
`false-positive`, or `false-negative`, records the detector result and
evaluation cost, and names its evidence reference. This keeps precision claims
auditable; a passing command alone is not treated as proof that a warning was
correct. A blocked evaluation may be retained as `unclassified`; it remains in
history but does not count toward the classified-observation threshold.

## Required promotion

Fleet evidence can recommend that criteria are satisfied, but it cannot approve
promotion. Required promotion needs a separate
`quality-runner-candidate-promotion-decision-v0.1` written by a human decision
owner and bound to the exact fleet provenance hash:

```bash
qr candidates promotion-check /path/to/repo \
  --candidate-id shared-workflow-classification-single-source \
  --fleet-evidence /private/path/candidate-fleet.json \
  --decision /path/to/repo/promotion-decision.json \
  --output /path/to/repo/promotion-receipt.json \
  --json
```

The check emits a `quality-runner-candidate-promotion-receipt-v0.1`. Promotion
is supported only when all of these are true:

- at least two independent repositories have true-positive occurrences;
- at least five classified, fresh observations exist;
- observed precision is at least 95%;
- maximum recorded evaluation cost is at most 30 seconds;
- classified evidence exists within the last 90 days;
- positive and negative fixtures are present;
- every occurrence has clear remediation;
- every repository occurrence describes the same candidate contract;
- the registry has reached `fleet-observation`;
- the decision is explicitly `approved` by a named human and matches the fleet
  provenance hash.

The supported receipt binds the reviewed candidate contract, so retaining old
observations or appending the final transition does not invalidate it. Add a
`fleet-observation -> required-gate` transition whose evidence names the
receipt, set the candidate's `promotion_receipt`, and link the same receipt
from the invariant:

```toml
[[quality_runner.invariants]]
id = "shared-workflow-classification"
description = "Every projection consumes the canonical workflow classification."
owner = "workflow-platform"
surfaces = ["workflow-record.ts", "projection-ui.ts", "projection-ledger.ts"]
command = "node --test tests/workflow-classification.test.mjs"
enforcement = "required"
candidate_id = "shared-workflow-classification-single-source"
promotion_receipt = "quality-runner-candidate-promotion-receipt.json"
```

A candidate-linked required invariant fails closed when the receipt is missing,
blocked, mismatched, contains failed criteria, or lacks explicit human
approval. Candidate-linked advisory invariants need no receipt.

## Compatibility

The registry and candidate commands are additive. Existing invariants without a
`candidate_id` keep their v0.1 behavior. Repositories can therefore migrate by
adding a registry and candidate linkage while leaving unrelated local required
gates unchanged. A reusable candidate should start advisory; do not label a
new candidate required merely because its originating regression is valuable.

The synthetic fixture under
`tests/fixtures/bug-learning/shared-workflow-classification/` models the
architectural pattern this lifecycle is meant to carry: one workflow record
feeds multiple projections, and the defect is independent reconstruction of
its semantic classification. The detector is fixture-only. Quality Runner does
not ship a generic heuristic that guesses application business meaning.
