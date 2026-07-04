# Research Readiness

Quality Runner is prepared as a DOI-grade software-methods artifact for
evidence-backed repository quality review. The citable release should archive
source code, CLI/MCP docs, artifact contracts, case-study evidence, dogfood
reports, release-smoke proof, and validation commands. Generated
`.quality-runner/` outputs from target repositories remain run artifacts unless
they are committed as examples.

## Artifact Map

| Surface | Purpose |
| --- | --- |
| `quality_runner/` | Core scan, standards, evidence, planning, CLI, and MCP implementation. |
| `docs/artifacts.md` | Versioned artifact contract and field-level guarantees. |
| `docs/case-study.md` and `docs/dogfood-report.md` | Public design narrative and self-audit evidence. |
| `docs/release.md` | Release process and package verification notes. |
| `docs/examples/` | Example handoff outputs for clean, blocked, and timeout cases. |
| `tests/` | Package-boundary, behavior, and compatibility tests. |

## Validation

Non-network release validation:

```bash
uv run ruff check quality_runner tests
uv run pytest -q
uv run quality-runner release-smoke --json
```

Full type/format readiness is not yet clean: `uv run ruff format --check
quality_runner tests` reports five files that need formatting, and
`uv run basedpyright quality_runner tests` reports pre-existing test typing
errors around monkeypatch objects. Treat those as blockers before DOI minting.

## Data Availability

Quality Runner artifacts generated against third-party repos should be treated
as run evidence, not automatically redistributed datasets. Commit curated example
handoffs only when they are intentionally public and contain no private paths or
secrets.

## DOI Gate

Author metadata records ORCID `https://orcid.org/0009-0006-0905-9633`.
Before minting a DOI, confirm the release tag and archived artifact boundary
match the release notes.
