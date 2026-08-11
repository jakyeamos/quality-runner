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

The maturity feed does not synthesize code-quality finding categories. Those
are an open set carried by each repository's fingerprinted
`code-quality-scan.json`; Pronto derives and renders native categories,
`skill:*` categories, and future categories directly from that report. A fleet
audit refreshes maturity dimensions and quality outcomes, while fresh category
totals require a current code-quality scan for the repository followed by
Pronto's quality refresh. Fleet maturity findings remain `dimension_gaps` and
must not be duplicated as code-quality findings.
The feed preserves every scored finding dimension in `dimension_scores` and up
to 64 non-passing `dimension_gaps`, which covers the current native, dynamic,
and agent-usability dimension set while keeping the private projection bounded.

The projection also carries `target_state` with the bounded target status,
reason, local and upstream SHAs, ahead/behind counts, and `safe_action`.
Non-passing dynamic execution is represented both by `dynamic_status` and by a
first-class `dynamic_verification` finding, so Pronto's blocker count and
explanation cannot disagree with QR's execution state.

The legacy per-repository `quality_status` field remains stable for v1
consumers. New presentation surfaces should use `quality_outcome`,
`quality_outcome_counts`, and `quality_outcome_taxonomy` so an operational
blockage is not mislabeled as a quality failure:

Presentation surfaces must render the bounded category label together with the
repository `disposition` and optional `next_step`; they must not render a raw
machine state as user-facing copy.

- `checks_failing` means an observed check failed or a non-dynamic blocker/P0
  finding exists.
- `verification_blocked` means timeout, setup, execution, or target-provenance
  conditions prevented a trustworthy verdict.
- `review_needed` means no blocker is known, but applicable evidence is below
  ideal or dynamic verification was not selected.
- `evidence_unknown` is the machine state for an evidence gap. Present it as
  `Evidence review required`, with concrete gap details; it is not a display
  string and does not mean a test failed.
- `healthy` means verification passed or was safely reused and every applicable
  dimension is maintained or validated.

Each repository projection also includes `agent_usability`. Its four independent
lanes preserve documentation-contract, tool-to-skill, behavior-evidence, and
freshness/portability states. Every applicable lane is also emitted as a stable
`agent_usability.*` dimension and contributes to the repository score, fleet
mean, dimension means, gaps, and certification decision. `growth_health` reports
bounded counts and coverage for documentation, tools, hosted or projected
skills, and declared skill families; its blocked, attention, and healthy states
score 0, 2, and 4 respectively and contribute through
`agent_usability.growth_health`. The producer never infers a passing relation
from file volume: the
repository must declare tool relationships in `.agents/agent-usability.json`.
A repository with no agent-facing tool or skill surface may declare
`applicability: not_applicable`, a non-empty `reason`, and empty `tools` and
`skills` arrays. Its lanes and growth score remain explicitly not applicable and
outside every score denominator while growth-health inventory still reports its
agent documentation structure.

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

The sanitized public consumer fixture is
`fixtures/contracts/public-adapters/pronto-maturity-feed.json`. Consumer tests
should read that fixture for schema compatibility; they must not copy a live
private fleet feed into the repository. The release boundary validates the
fixture and blocks publication when it is missing or contains local markers.
