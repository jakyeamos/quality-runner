# Security and approval constraints

Last reviewed: 2026-08-02

Quality Runner is local-first. It may read bounded repository files and write
`.quality-runner/runs/<run-id>/` artifacts in a target repository. It must not
call remote services, contact model providers, collect credentials, edit target
source, create commits, push, publish, or execute remediation by default.

Generated evidence can contain sensitive repository details. Secret-like
literals must be redacted before persistence, but artifacts are not a promise
that every possible secret is removed. Do not commit `.env` files, keys,
credentials, raw prompts, transcripts, private paths, or unpublished evidence.

Discovered quality commands are evidence-only unless the caller explicitly
authorizes disposable execution. Disposable worktrees must be isolated,
verified, and disposable; the ordinary source checkout is protected. A missing
credential, unavailable network, stale baseline, failed redaction, or missing
provenance is an explicit unknown or blocked result, never a successful gate.

Release publication, tagging, trusted publishing, Homebrew changes, and remote
workflow changes require human review and the release checklist.
