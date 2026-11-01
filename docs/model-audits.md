# Refreshable model audits

Use `qr model-audit` to retain an audit specification, source inputs, reviewer
settings, responses and separate verification evidence across model upgrades.
A model upgrade is a reason to consider refreshing the audit. Advisory or
feasibility questions alone do not authorize audit preparation, provider
execution or fleet discovery; begin those steps with an explicit scoped request.
Useful verified findings support a proposal for implementation through the
repository's existing authorized change workflow.

Quality Runner owns the evidence. It does not call model providers, enforce
their execution budget, execute tests from an audit, or fix target source.
The CLI and `quality_runner_model_audit` MCP tool share one implementation.
Pronto can project explicit repository/run selections without creating a second
remediation queue.

## Save the audit specification

Keep a versioned profile with shared criteria and each repository's purpose,
constraints and explicit input paths. Paths are literal repository-relative
file or directory prefixes, not globs. This example assumes a tracked `src/`:

```json
{
  "schema": "quality-runner-model-audit-profile/v1",
  "id": "service-maintenance",
  "revision": "1",
  "purpose": "Maintain the service's documented public behavior",
  "constraints": ["Preserve public APIs", "Prefer supported existing dependencies"],
  "criteria": [
    {"id": "correctness", "prompt": "Find concrete failures in intended behavior, including boundaries."},
    {"id": "maintainability", "prompt": "Find justified simplifications with a concrete maintenance benefit."},
    {"id": "verification", "prompt": "Find important behavior that current checks do not establish."}
  ],
  "include_paths": ["src"],
  "exclude_paths": []
}
```

Save reviewer settings separately; set the actual model identifier available in
your execution environment. The identifiers below are illustrative:

```json
{
  "reviewer_id": "reviewer-run-001",
  "model": "MODEL_ID",
  "provider": "PROVIDER_ID",
  "effort": "high",
  "harness": "audit-harness/1",
  "tools": ["read", "search"],
  "budget": {"seconds": 600, "max_findings": 20}
}
```

The input JSON Schema is `quality_runner/schemas/model-audit-input.schema.json`.
Strict runtime checks additionally enforce normalized paths, unique criteria,
exact bindings and local-file safety.

## Prepare, review and verify

```sh
qr model-audit prepare /path/to/repo --run-id audit-001 \
  --profile /path/to/profile.json --reviewer /path/to/reviewer.json --json
```

The result names a fresh-review packet and private source copy under
`.quality-runner/runs/audit-001/`. Only selected tracked files are copied:
untracked, excluded and generated QR files are omitted. Snapshots reject
symlinks, special files, files over 4 MB, totals over 32 MB and more than 10,000
files. They capture working file bytes, including tracked edits, and record the
observed Git HEAD; a dirty snapshot is not equivalent to that commit. Copies
retain bytes, not executable modes or a runnable dependency environment.

Invoke the declared reviewer in a fresh context with the generated packet.
Keep prior reviews out of that context and restrict its filesystem scope in
the provider harness. QR records declared identity, effort and budget; it does
not attest the actual model, timing, isolation or hidden context. Use the
generated `review-adapter-response.template.json`, set `adapter.name` to the
declared `reviewer_id`, and save the completed response inside the run directory.

```sh
qr model-audit record /path/to/repo --run-id audit-001 \
  --response /path/to/repo/.quality-runner/runs/audit-001/response.json --json
```

Even a model's "confirmed" finding remains unverified. A separate verifier
must reproduce or adjudicate it, retain a bounded UTF-8 evidence file directly
inside that run, and submit this receipt with actual digests from the result
and evidence bytes:

```json
{
  "schema": "quality-runner-model-audit-verification/v1",
  "run_id": "audit-001",
  "manifest_digest": "SHA256_FROM_MODEL_AUDIT_RESULT",
  "response_digest": "SHA256_FROM_MODEL_AUDIT_RESULT",
  "verifier_id": "independent-verifier-001",
  "independent": true,
  "findings": [{
    "fingerprint": "FINGERPRINT_FROM_RESPONSE",
    "canonical_key": "stable-identity-of-the-failure-mechanism",
    "criterion_id": "correctness",
    "verdict": "verified",
    "method": "Describe the independent reproduction or adjudication",
    "evidence": [{"path": "reproduction.txt", "sha256": "SHA256_OF_EVIDENCE_BYTES"}]
  }]
}
```

```sh
qr model-audit verify /path/to/repo --run-id audit-001 \
  --verification /path/to/repo/.quality-runner/runs/audit-001/verification.json --json
qr model-audit report /path/to/repo --run-id audit-001 --json
```

Use the same canonical key only for the same mechanism in the same profile.
Different wording or fingerprints can then match known findings. Identity is
adjudicated, not inferred from text similarity. Receipts are append-only and
revalidated on read; contradictory verdicts or identities produce a disputed
finding. Independence is an explicit attestation, not a cryptographic proof.
Hashes bind retained evidence; they do not prove the evidence's conclusion.

## Refresh with another model

```sh
qr model-audit prepare /path/to/repo --run-id audit-002 \
  --profile /path/to/profile.json --reviewer /path/to/new-reviewer.json \
  --baseline-run-id audit-001 --reuse-inputs-from audit-001 --json
```

Repeat record, verify and report. Reusing inputs preserves the exact source
bytes and requires the identical profile. Omit `--reuse-inputs-from` to audit
current code while retaining prior findings through `--baseline-run-id`.

Reports distinguish newly verified, known, disputed, unverified and not
reobserved findings. "Newly verified" means the current finding has a verified
verdict and no previously verified canonical identity in its linked lineage.
It does not mean the current model first discovered the problem: an earlier
unverified claim may describe it, and unmatched identities remain separate.
Inspect prior claims and adjudicated identities before attributing discovery.
Reports may be read before verification; keep their unverified state explicit.
**Omission never resolves a finding**, even after repeated
refreshes. Resolution and accepted risk remain in the existing remediation
workflow; this audit ledger grants no implementation authority.

Comparison states are initial, fixed-snapshot, rolling-code or
incompatible-profile. Changed provider, effort, harness, tools, budget, profile
or source are explicit confounders. Even a controlled single comparison cannot
establish model superiority; repeat matched runs before drawing that conclusion.
The report concerns retained inputs and does not assert current workspace health.

## Fleet readback and retention

```json
{
  "schema": "quality-runner-model-audit-selection/v1",
  "repositories": [{"repo_path": "/path/to/repo", "run_id": "audit-002"}]
}
```

```sh
qr model-audit fleet --selection /path/to/selection.json --json
```

Selections contain 1–256 explicit absolute repository/run pairs. There is no
implicit latest run or fleet discovery. Missing or invalid evidence yields
partial coverage and exit 1, never a zero-findings assessment. Recurring
criteria mean independently verified findings share the same criterion text;
they do not establish a common root cause across repositories.

Normal QR retention preserves audit runs, including incomplete or malformed
ones, because deleting any baseline breaks comparison lineage. Each snapshot
is bounded, but total retained storage grows per run. Archive a complete lineage
under an explicit operator decision before removing it; this command surface
does not perform archival or deletion. A lineage is bounded at 64 runs.

`run-manifest.json` identifies the run as mode `model-audit` for consumers.
The dedicated report is authoritative for model comparison. It must not
replace deterministic quality gates, maturity, release checks or existing
remediation status. All evidence is local and may contain private source and
findings; publishing or exporting it requires a separate decision.
