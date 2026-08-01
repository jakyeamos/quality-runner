# Security review obligations artifact

Quality Runner emits `security-review-obligations.json` beside the other run
artifacts whenever a run produces security analysis. This is the machine-
readable contract for QR-generated security review gates; it is distinct from
ordinary remediation slices and is not a deterministic pass/fail result.

Each obligation records its stable gate ID, corresponding remediation and audit
IDs, scope, review instructions, completion criteria, and deterministic
candidate references. The `source` field identifies `security-scan.json` and
the `agent_review_gates` selection that produced the records.

The artifact is generated from the current security scan and must not be edited
by an external executor. Reviewers record decisions through the existing
resolution-ledger or gate-controller workflow, preserving the distinction
between review-required, fixed, false-positive, accepted-risk, and blocked
outcomes.
