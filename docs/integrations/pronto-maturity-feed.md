# Pronto maturity feed

Quality Runner is the canonical owner of fleet environment-legibility maturity.
Pronto must read this fixed private JSON path:

```text
~/.quality-runner/fleet-audit/current/maturity.json
```

The feed schema is `quality-runner-maturity-feed/v1`. It is published only
after the selected immutable audit snapshot has passed deterministic replay,
coverage, provenance, and privacy validation. The stable file is atomically
replaced; snapshots remain available at
`~/.quality-runner/fleet-audit/<audit-id>/`.

To republish an existing valid QR snapshot:

```bash
qr fleet audit feed --audit-id AUDIT_ID --json
```

The feed contains the QR audit ID, timestamp, replay status, provenance hash,
fleet counts, aggregate maturity distributions, unresolved measurement gaps,
and redacted per-repository projections. Each repository projection includes a
bounded `dimension_gaps` list so Pronto can explain scores such as
`change_surface_coverage` and conditional `skill_contract_quality` without
reading or generating repository artifacts. It does not contain prompts, source
code, diffs, transcripts, credentials, or raw command output. Local consumers
may use the private repository-identity field to match a projection to a
checkout; public exports must use only aggregate projections.

The older leverage audit directory is historical evidence only. It is not a
source for the current feed.
