# Pronto maturity feed

Quality Runner is the canonical owner of fleet environment-legibility maturity
and the freshness boundary for the Mac Control ideal-state lane. A complete
`qr fleet audit run` includes a bounded, static Mac Control audit by default;
the two lanes keep their own evidence and scores, but `qr fleet audit feed`
publishes them as one coordinated checkpoint.

It also owns the static evidence for two repository-evolution gates:

- `developer_legibility` measures eight lanes: orientation, navigation and
  traceability, architecture visibility, semantic naming, public contracts,
  rationale and invariant comments, executable understanding, and bounded
  ownership/freshness. Static evidence is capped at level 3; level 4 requires
  commit-bound newcomer-exercise evidence.
- `change_surface_hotspots` combines Git co-change, local structural coupling,
  and repeated-concept signals. A hotspot is reported only when at least two
  evidence families agree; “tokenization” is a remediation hypothesis, not a
  score input.

These dimensions are deliberately separate from `change_surface_coverage`.
The matrix answers whether known add/change/remove surfaces have owners and
validation. The hotspot audit answers where future changes are likely to
amplify or become difficult to remove.
Pronto should read this coordination pointer first:

```text
~/.quality-runner/fleet-audit/current/maturity-checkpoint.json
```

The pointer uses schema `quality-runner-maturity-checkpoint/v1` and references
an immutable bundle under
`~/.quality-runner/fleet-audit/current/checkpoints/<checkpoint-id>/`. The
bundle contains the QR maturity feed, the Mac Control ideal-state report, and
the Mac Control summary. The pointer records hashes for the two scored
components and is atomically replaced after the bundle is complete.

The existing QR feed remains at this compatibility path:

```text
~/.quality-runner/fleet-audit/current/maturity.json
```

The feed schema is `quality-runner-maturity-feed/v2`. It is published only
after the selected immutable audit snapshot has passed deterministic replay,
coverage, provenance, and privacy validation. The stable file is atomically
replaced; snapshots remain available at
`~/.quality-runner/fleet-audit/<audit-id>/`.

The coordinated checkpoint binds the QR and Mac Control audit IDs, the exact
`as_of` timestamp, the repository population, and every primary observed
commit. Its `publication_status: "ready"` means the evidence is coherent and
replay-valid; `quality_status: "ready_with_blockers"` is still possible when a
repository's quality or Mac Control evidence failed or needs review. Consumers
must evaluate the checkpoint's seven-day freshness window separately from its
quality status. A missing pointer is legacy separate-feed evidence. An invalid
pointer is blocked and must not silently fall back to the two sidecars.

To republish an existing valid QR snapshot:

```bash
qr fleet audit feed --audit-id AUDIT_ID --json
```

For the normal coordinated flow, run and publish the same immutable QR
snapshot:

```bash
qr fleet audit run --all --projects-root /path/to/projects --json
qr fleet audit replay --audit-id AUDIT_ID --json
qr fleet audit feed --audit-id AUDIT_ID --json
```

Use `--no-mac-control` only for an explicitly legacy or diagnostic QR feed.
`--mac-control-live` opts into foreground Mac Control checks in the same QR
checkpoint; live execution is never implicit. The standalone
`qr fleet mac-control audit ...` commands remain available for targeted
replay, inspection, and compatibility publication, but they do not create a
coordinated checkpoint without a containing QR audit.

When Pronto's registry is the population authority, provide an owner-reviewed
`quality-runner-fleet-scope/v1` manifest to `qr fleet audit run` with
`--scope-manifest`, a bounded common `--projects-root`, `--dynamic`, and
`--no-changed-only`. The private inventory retains the manifest hash, authority,
eligible count, and excluded count; the feed publishes only bounded aggregate
population evidence.

For a whole-inventory audit of one repository standard, run the static scoped
lane instead:

```bash
qr fleet audit run --all --projects-root /path/to/projects \
  --standard matrix-maintenance --json
qr fleet audit run --all --projects-root /path/to/projects \
  --standard developer-legibility --json
qr fleet audit run --all --projects-root /path/to/projects \
  --standard long-running-tasks --json
```

The snapshot contains `standard-report.json` with one redacted row per audited
repository. It is deliberately not a canonical maturity-feed input: a
one-standard result cannot stand in for the full maturity inventory, so
`qr fleet audit feed` rejects it. Replay and inspect the report directly.

The feed contains the QR audit ID, timestamp, replay status, provenance hash,
fleet counts, aggregate maturity distributions, unresolved measurement gaps,
measurement confidence, and redacted per-repository projections. Confidence is
`high` only when the exact eligible population is attested, every repository has
complete static and full dynamic evidence, no measurement gap remains, and the
published snapshot passes deterministic replay. A known failing check is a
measured maturity result, not a confidence gap; the same applies to a static
stale, blocked, or unknown state when the rubric assigns a numeric score. A
static assessment with no numeric score remains unresolved. Each repository projection includes a
`quality-runner-repository-maturity/v2` model. Dimensions aggregate through
explicit capabilities before its seven stable pillars are weighted, so
overlapping checks do not give one capability extra influence. The projection keeps
the legacy flat `dimension_scores` and its arithmetic `source_dimension_mean`
for diagnosis and migration, but neither is the holistic score.

The pillars cover correctness/reliability, security/privacy/supply chain,
maintainability/evolvability, operability/release safety, user-facing quality,
human/agent usability, and governance/sustainability. Required capabilities
remain applicable even when measurement is missing. Conditional capabilities
carry explicit `applicable`, `not_applicable`, or `unknown` state and are never
silently zeroed or excluded. Coverage, freshness, missing capabilities, unknown
applicability, diagnostic dimensions, and unmapped dimensions stay separate
from the score. One detector can establish a provisional capability score but
cannot claim complete pillar evidence. Only a finding marked
`confirmed_critical_risk: true` in correctness, security, or operability
applies the 2.0 cap; operational blockage, P0 priority, and blocker severity
remain quality-outcome signals without automatically asserting critical risk.

The v2 producers cover reliability/resilience, data integrity and migration,
dependency/vulnerability risk, secrets/privacy, artifact supply chain,
language-neutral code health, compatibility/migration, runtime observability,
accessibility, performance, critical user journeys, holistic web readiness,
ownership continuity, maintenance continuity, and conditional
license/contribution readiness. Web evidence reuses the bounded web-readiness
checks, while security evidence reuses the security-capability detector.

The model draws on the ISO/IEC 25010 product-quality characteristic structure,
OpenSSF Scorecard's risk-sensitive aggregation and explicit unknown results,
SLSA's progressive supply-chain assurance, OpenSSF Best Practices coverage of
governance/accessibility/testing/security, and DORA's practice of presenting a
blended delivery score together with its component metrics. Primary references:
[ISO/IEC 25010:2023](https://www.iso.org/standard/78176.html),
[OpenSSF Scorecard](https://github.com/ossf/scorecard),
[SLSA](https://github.com/slsa-framework/slsa),
[OpenSSF Best Practices Badge](https://github.com/ossf/best-practices-badge), and
[DORA Quick Check](https://dora.dev/insights/quickcheck-updates/).

Each repository projection also includes a
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
agent-usability, `developer_legibility`, `change_surface_hotspots`, and
`matrix_maintenance` dimension set while keeping the
private projection bounded. `matrix_maintenance` is assessed by the complete
fleet audit and contributes to repository scores, fleet means, gaps,
certification decisions, and Pronto maturity remediation. The one-standard
`--standard matrix-maintenance` run remains a diagnostic report and cannot
replace the complete feed.

The complete audit also carries `long_running_task_observability` and
`long_running_task_optimization`. QR only applies them when an explicit
long-running-task annotation or a concrete timeout qualifies a task; task names
alone are insufficient. Missing machine-readable progress/diagnostics or
optimization evidence becomes an ordinary maturity gap. Pronto imports those
gaps into deferred maturity remediation; it does not treat them as an immediate
blocker or automatically modify the task.

The feed also carries `diagnosability.stable_error_codes` when a repository has
a supported runtime source surface. Quality Runner assesses this dimension from
bounded source, documentation, and test evidence: declared machine-readable
codes are discoverable evidence; propagated codes are structured evidence; and
documented, tested, uniquely identified, propagated codes reach the maintained
4/4 level. Repositories without runtime source are explicitly
`not_applicable`; source repositories without the contract score 0 rather than
receiving a pass. Pronto renders this as a maturity dimension and remediation
gap only; it must not treat the score as a fresh test result or as proof that
every runtime failure uses the contract.

The projection also carries `target_state` with the bounded target status,
reason, local and upstream SHAs, ahead/behind counts, and `safe_action`.
Non-passing dynamic execution is represented both by `dynamic_status` and by a
first-class `dynamic_verification` finding, so Pronto's blocker count and
explanation cannot disagree with QR's execution state.

Each repository projection also carries `behavior_assurance`, derived from the
repository's `.pronto/behavior-assurance.json` contract and immutable receipts.
The fleet feed includes a bounded aggregate of applicability, result, scenario,
and gap counts. Missing or invalid contracts and missing, failed, stale,
target-mismatched, or under-powered receipts remain non-ready; only current
passing Tier-0 evidence or a valid explicit not-applicable contract is
release-ready. See
[Pronto behavior assurance](./pronto-behavior-assurance.md) for the artifact and
carry-forward contract.

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
`agent_usability.*` dimension and contributes through four consolidated
capabilities: documentation contract, tool/skill coverage, behavior evidence,
and routing/portability. `growth_health` remains a diagnostic inventory of
documentation, tools, hosted or projected skills, and declared skill families;
it no longer adds a fifth human/agent score. The producer never infers a passing
relation from file volume: the
repository must declare tool relationships in `.agents/agent-usability.json`.
A repository with no detected agent-facing tool, skill, or agent-documentation
surface is explicitly not applicable. A repository may also declare
`applicability: not_applicable`, a non-empty `reason`, and empty `tools` and
`skills` arrays. Its lanes stay outside every score denominator while
growth-health inventory still reports its agent documentation structure.

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

The private finding artifact retains bounded gate detail under the finding's
`audit` field. The published Pronto projection intentionally keeps only the
dimension score, status, bounded gap message, and repository identity; it does
not publish source code, diffs, transcripts, or raw command output. Static
validation is not semantic proof: a valid line anchor can still point to a
misleading explanation, and a hotspot still requires reviewer judgment before
introducing a shared abstraction.

The sanitized public consumer fixture is
`fixtures/contracts/public-adapters/pronto-maturity-feed.json`. Consumer tests
should read that fixture for schema compatibility; they must not copy a live
private fleet feed into the repository. The release boundary validates the
fixture and blocks publication when it is missing or contains local markers.
