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
| `docs/upgrade.md` | Cutover, compatibility, and non-destructive rollback policy. |
| `docs/case-study.md` and `docs/dogfood-report.md` | Public design narrative and self-audit evidence. |
| `docs/release.md` | Release process and package verification notes. |
| `docs/examples/` | Example handoff outputs for clean, blocked, and timeout cases. |
| `tests/` | Package-boundary, behavior, and compatibility tests. |

## Validation

The current release candidate uses the locked validation ladder in
[`docs/release.md`](docs/release.md). Run it against the release commit:

```bash
uv sync --locked --all-groups
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked basedpyright
uv run --locked vulture quality_runner quality_evidence_contract repo_quality_certifier tests scripts --min-confidence 70
uv run --locked quality-runner release-smoke --json
```

Do not treat historical format or type failures as current release evidence.
The built-distribution CI and release workflows repeat the package checks from
the committed lockfile; record their result for the exact archived commit.

## Data Availability

Quality Runner artifacts generated against third-party repos should be treated
as run evidence, not automatically redistributed datasets. Commit curated example
handoffs only when they are intentionally public and contain no private paths or
secrets.

## DOI Gate

Author ORCID is recorded in `CITATION.cff` and `.zenodo.json`.
Before minting a DOI, confirm the release tag and archived artifact boundary
match the release notes.
