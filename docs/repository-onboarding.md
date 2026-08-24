# Repository Onboarding Readiness

`qr onboarding check` is the executable consumer for the fleet repository-
onboarding matrix. It does not infer readiness from file presence or prose. It
fails closed unless approved producers provide current evidence for every
required surface and an explicit outcome for every conditional surface.

```bash
qr onboarding check /path/to/repository \
  --matrix ~/.agents/repository-onboarding-change-matrix.json \
  --evidence /path/to/repository/.quality-runner/onboarding-evidence.json \
  --output /path/to/repository/.quality-runner/onboarding-check.json \
  --json
```

The command exits `0` only for `readiness: ready`. Missing, malformed, stale,
dirty, partial, unknown, blocked, warning-bearing, or producer-untrusted
evidence exits `1`. Invalid CLI usage exits `2` through the normal argument
parser.

The check is read-only by default. It writes only when `--output` is explicit,
and never runs project commands, installs dependencies, edits source, creates a
commit, or changes a remote. The output path is caller-controlled; generated
receipts should normally stay under the ignored `.quality-runner/` directory.

## Inputs and authority

The command reads three sources:

1. The live target repository, for its current branch, commit, and cleanliness.
2. The fleet matrix, whose SHA-256 digest binds the policy being evaluated.
3. A normalized evidence envelope using
   `quality-runner-onboarding-evidence/v1`.

The envelope is an assembly format, not a self-attestation. Each surface names
its producer and producer version. The matrix allowlists producers per surface;
an unknown producer blocks readiness. The repository-level target and every
surface target must match the live branch and commit exactly. A conditional
surface may use `not_applicable` only with a non-empty reason and current
exact-ref evidence.

The distributed input schema is
`quality_runner/schemas/onboarding-evidence.schema.json`. A minimal surface has
this shape:

```json
{
  "surface_id": "repository-identity-and-product-truth",
  "status": "passed",
  "producer": {"id": "quality-runner", "version": "0.7.0"},
  "observed_at": "2026-08-24T12:00:00Z",
  "target": {
    "branch": "codex/example",
    "head_sha": "0123456789abcdef0123456789abcdef01234567"
  },
  "evidence": ["receipt:repository-identity"]
}
```

The producer-specific content belongs in `details`; the generic validator does
not reinterpret or cryptographically authenticate a foreign producer's raw
files. A trusted onboarding workflow is responsible for collecting the actual
approved producer receipts into one envelope. The validator then enforces the
allowlists, exact-ref bindings, policy digest, and surface-specific checks. The
executable-quality surface additionally verifies the digest and contents of its
Quality Runner receipt. A hand-authored envelope is therefore not an
independent attestation of foreign tool execution.

## Executable quality evidence

`executable-quality-evidence` has additional mandatory semantics. Its details
must prove all of the following:

- one canonical local verification command;
- the same command passed in CI for the exact branch and commit;
- locked dependency resolution in CI;
- zero warnings and zero errors;
- a disposition for lint, typecheck, tests with coverage, dead-code,
  domain-validation, security, and build gates;
- a passing clean fixture;
- intentional rejection of a seeded violation, a missing tool, and a skipped
  required adapter;
- no accepted warning or finding baseline; and
- an untampered `quality-runner-gate-verification-v0.2` receipt inside the
  repository, proving required gates actually ran in an authorized disposable
  context for the exact ref.

A gate may be not applicable only when its record contains an explicit reason.
The repository cannot become ready from a historical baseline, a local-only
pass, CI on another commit, a discovered-but-unexecuted command, or a warning-
only result.

## Output contract

The check result uses `quality-runner-onboarding-check/v1`, distributed as
`quality_runner/schemas/onboarding-check.schema.json`. It records:

- live repository identity and dirty-path count;
- matrix and evidence digests;
- contract and provenance checks;
- one result per required or conditional surface;
- blocking check and surface identifiers; and
- `ready` or `not_ready` as the only readiness outcomes.

Absolute local paths are included for diagnosis, so the receipt is local
operational evidence, not a privacy-safe publication artifact.

## Negative and boundary behavior

The contract is tested with complete, missing, stale-ref, stale-policy,
warning-bearing, missing-negative-control, tampered-receipt, and unexplained
conditional evidence. Adding a new required or conditional matrix surface
automatically creates a blocker until the surface is registered, assigned an
approved producer, and represented in the current envelope.

The validator does not create repositories or producer evidence. It is the
final admission decision after those bounded workflows run. That separation
keeps Quality Runner read-only while making the fleet's onboarding policy
enforceable by exit code and a versioned machine receipt.
