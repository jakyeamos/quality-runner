# Security and privacy constraints

last_reviewed: 2026-07-22

Quality Runner is local-first. Target repositories are read-only inputs by
default; providers, deployments, remotes, and publication are outside the
normal audit path.

- Never read, persist, or transmit credentials, tokens, private prompts,
  transcripts, raw diffs, or unrelated repository content.
- Treat run artifacts as potentially sensitive even after redaction; keep them
  local and inspect before sharing.
- Redact secret-like evidence before fingerprinting or persisting it.
- Do not add `.env`, private keys, credential files, or machine-specific paths
  to the repository.
- Release, PyPI, GitHub, and external security-reporting actions require
  explicit human review.

The canonical policy is [SECURITY.md](../../SECURITY.md). Threat assumptions
and review obligations live in [docs/threat-model.md](../../docs/threat-model.md)
and [docs/security-review-obligations.md](../../docs/security-review-obligations.md).
