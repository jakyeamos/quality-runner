# Isolated-change custody validation

Quality Runner provides the independent, read-only validation edge for the
isolated-change-workflow custody ledger. The workflow remains the authority for
receipt signing, lease mutation, adoption, integration locking, and branch or
worktree cleanup. Pronto consumes the same projection but cannot use it as
mutation permission.

Run the validator against one repository:

```bash
qr fleet custody validate /path/to/repository --json
```

The output schema is `quality-runner-custody-validation/v1`. It combines fresh
Git worktree, branch, head, cleanliness, operation-marker, and open-file
evidence with the local receipt files under the repository's common Git
directory. It is explicitly marked:

```json
{
  "read_only": true,
  "implementation_allowed": false,
  "mutation_risk": "read-only"
}
```

## State and disposition

`state` is the lifecycle projection:

`active`, `paused`, `stale`, `adoptable`, `contested`, `integrating`, `closed`,
or `unknown`.

`disposition` and `dispositions` are the evidence reasons. They are intentionally
more granular than `unknown`, including:

- `legacy_unsigned_receipt`: use the bounded legacy owner-return or adoption review.
- `receipt_malformed`: preserve the receipt and repair it through the workflow owner.
- `receipt_integrity_invalid`: preserve a known receipt whose integrity evidence is missing or malformed.
- `receipt_schema_unsupported`: preserve the lane and upgrade the producer.
- `branch_binding_mismatch` or `head_binding_mismatch`: re-read the exact live Git binding.
- `dirty_worktree`, `open_files_observed`, or `git_operation_active`: adoption is blocked by live activity.
- `live_git_evidence_unavailable`: retry with complete evidence; no custody decision is authorized.
- `adoption_ready`: the negative evidence supports an exact-head adoption claim.

`unknown` is only a lifecycle state. A validator result without a concrete
disposition and `next_action` is invalid. A legacy or unsupported receipt never
becomes adoptable merely because its timestamp is old. A clean expired lane can
be `adoptable` while still carrying `receipt_integrity_unverified`, because QR
does not possess the workflow's local HMAC key and therefore cannot claim
cryptographic identity.

The sanitized public contract fixture is
`fixtures/contracts/public-adapters/pronto-custody-validation.json`. It uses
synthetic paths and receipt identities; live private fleet data must not be
committed or published.
