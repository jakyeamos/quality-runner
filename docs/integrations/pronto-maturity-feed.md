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
reading or generating repository artifacts.

Each repository projection also includes `agent_usability`. Its four independent
lanes preserve documentation-contract, tool-to-skill, behavior-evidence, and
freshness/portability states. `growth_health` reports bounded counts and coverage
for documentation, tools, hosted or projected skills, and declared skill
families. The producer never infers a passing relation from file volume: the
repository must declare tool relationships in `.agents/agent-usability.json`.
A repository with no agent-facing tool or skill surface may declare
`applicability: not_applicable`, a non-empty `reason`, and empty `tools` and
`skills` arrays. Its lanes remain explicitly not applicable while growth-health
inventory still reports its agent documentation structure.

Hosted `contract_path` entries also drive conditional skill-contract quality.
This keeps provider-edge and nested hosted skills inside the same bounded static
review instead of limiting quality evidence to the conventional `skills/`
directory.

The feed does not contain prompts, source code, diffs, transcripts, credentials,
or raw command output. Local consumers may use the private repository-identity
field to match a projection to a
checkout; public exports must use only aggregate projections.

The older leverage audit directory is historical evidence only. It is not a
source for the current feed.
