# Quality Runner system map

Status: proposal catalog; existing child Compasses remain draft/open and are
not ratified by this map.

## Decision record

- Selected form: ICM System map. Quality Runner crosses audit/evidence
  production, review/handoff projection, downstream consumer contracts, and a
  top-level certifier surface.
- Rejected smaller form: root context alone. It would hide the difference
  between producing evidence and presenting or consuming it.
- Authority: `.project-compass/`, `.agents/context/architecture.md`, and the
  evidence contract.
- Existing user gate: the active quality-runner root quiz remains the intent
  gate for child boundaries.

## Universe inventory

- **live candidates:** `quality_runner/`, `quality_evidence_contract/`,
  `repo_quality_certifier/`, fixtures, docs, packaging, scripts, and tests.
- **known draft boundaries:** audit/evidence engine, review/handoff output, and
  consumer contracts already exist as draft Compass entries.
- **unknown:** whether `repo_quality_certifier/` is a consumer-contract
  adapter, part of audit evidence, or an independently maintained child.
- **support layers:** artifacts, fixtures, packaging, scripts, and tests are
  not children by folder presence alone.

## Proposed target tree

```text
map/
├── AGENTS.md
├── CONTEXT.md
├── _meta/schema.md
├── _templates/object.md
└── objects/
    ├── CONTEXT.md
    └── _index.md
```

Candidate clusters:

- **audit-evidence-engine** — inspect, normalize, and produce explainable
  evidence without mutating the target.
- **review-handoff-output** — turn findings into review-ready plans and
  handoff artifacts.
- **consumer-contracts** — preserve downstream adapter and integration
  compatibility.
- **repo-quality-certifier** — unresolved placement; do not ratify yet.

## First-order impact

- **Hits:** changes to audit semantics, review projections, consumer schemas,
  or certification behavior hit the relevant cluster and root Compass.
- **Does not hit:** a target repository's remediation implementation remains
  outside Quality Runner's ownership.

## Open decisions

1. Where does `repo_quality_certifier/` belong?
2. Does the consumer boundary include all documented integrations or only
   public adapter contracts?
3. Which evidence proves each draft child is aligned?

