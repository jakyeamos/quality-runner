# Web-readiness evidence contract

Quality Runner owns a categorical, versioned web-readiness report at
`.quality-runner/web-readiness.json`. The report is separate from numeric
maturity: it records `ready`, `warnings`, `blocked`, `unknown`, or
`not_applicable` and never authorizes implementation.

Run the source and artifact inspection with:

```bash
qr web-readiness /path/to/repository --json
```

The command exits non-zero for `blocked` and `unknown`. A source-only run stays
`unknown` until project-owned browser evidence proves route, console, network,
asset, and rendered-document behavior.

## Repository policy

Declare applicability and artifact budgets in `.quality-runner.toml`:

```toml
[quality_runner.web_readiness]
applicability = "public_web" # public_web, internal_web, not_applicable, unknown
reason = "Public product surface"
routes = ["/", "/about"]
build_roots = [".next/static/chunks", "dist/assets"]
bundle_budget_gzip_bytes = 200000
total_bundle_budget_gzip_bytes = 800000
```

`not_applicable` requires a reason. Missing or invalid applicability remains
`unknown`; QR does not infer that an application is public from framework or
file names. Public and internal web profiles share the baseline checks. Polish
checks such as meta descriptions and social images are warnings rather than
release blockers.

## Evidence levels

- `source_inferred`: language, image alternatives, favicon declarations,
  title and heading declarations, conventional not-found routes, and polish
  metadata found in supported source files.
- `artifact_inspected`: per-file and total gzipped JavaScript budgets measured
  from configured production build roots.
- `browser_rendered`: reserved for a project-owned browser producer that proves
  rendered behavior without identifying a deployment.
- `deployment_verified`: a project-owned browser producer binds route evidence
  to an exact repository HEAD and deployment URL.

A stronger level does not retroactively upgrade weaker checks. Consumers must
enforce their configured minimum level rather than treating a source pass as a
deployment pass.

## Deployment evidence producer

Projects keep their existing Playwright or equivalent browser setup and emit
`quality-runner-web-deployment-evidence/v1`. QR validates the schema, exact HEAD
commit, deployment target, and route records before importing them:

```json
{
  "schema": "quality-runner-web-deployment-evidence/v1",
  "observed_at": "2026-08-10T20:00:00Z",
  "target": {
    "kind": "deployment",
    "commit": "0123456789abcdef",
    "url": "https://preview.example.test",
    "provider": "project-ci",
    "deployment_id": "preview-123"
  },
  "routes": [
    {
      "route": "/",
      "status_code": 200,
      "title": "Home",
      "primary_heading_count": 1,
      "html_lang": "en",
      "missing_alt_count": 0,
      "console_error_count": 0,
      "network_error_count": 0,
      "asset_error_count": 0,
      "favicon_loaded": true,
      "meta_description": "Home page",
      "og_image": "https://preview.example.test/og.png"
    },
    {
      "route": "/qr-not-found-probe",
      "not_found_probe": true,
      "status_code": 404
    }
  ]
}
```

Import it with:

```bash
qr web-readiness /path/to/repository \
  --deployment-evidence /path/to/web-deployment-evidence.json --json
```

The JSON Schemas are distributed as
`quality_runner/schemas/web-readiness.schema.json` and
`quality_runner/schemas/web-deployment-evidence.schema.json`.

## Proactive performance budgets

Adopt this lane when a feature changes loading, interaction, assets, dependencies,
data access, or delivery cost. Start with affected journeys and existing acceptance
criteria. Measure a representative production build before choosing limits; a
baseline describes current behavior and does not by itself establish acceptability.
Document the user need, owner, conditions, and uncertainty. Keep noisy or unproven
checks `warn` until the producer is reliable. Do not require a universal speedup,
zero bundle growth, or perfect audit score.

Artifact budgets above retain legacy defaults of 200000 bytes per file and
800000 bytes total when omitted. Their evidence now labels `budget_origin` as
`legacy_defaults`, `mixed`, or `repository` and `measurement_scope` as
`build_artifact_inventory`. Summing gzipped build files does not measure which
chunks a route loads, HTTP transfer encoding, parse/execution cost, or user speed.
New runtime budgets have no default thresholds.

Declare one budget per metric and scenario. This example is illustrative; choose
values from the project's acceptance criteria and representative measurements:

```toml
[[quality_runner.web_readiness.performance_budgets]]
id = "home-mobile-lcp"
metric = "lcp_ms"
maximum = 2500
statistic = "median"
min_samples = 3
max_age_hours = 24
policy = "warn"
owner = "web-team"
rationale = "Provisional home loading target; validate on supported mobile devices"
method = "navigation"
scenario = { route = "/", journey = "home-load", device = "mobile", network = "slow-4g-v1", cpu = "4x-v1", cache = "cold", dataset = "demo-v1" }
```

Every field is required; IDs must be unique. Supported metrics are `lcp_ms`,
`inp_ms`, `cls`, and `js_transfer_bytes`; thresholds and samples are finite,
non-negative numbers (integer bytes for transfer). `statistic` is `median` or
`max`, `min_samples` is 1–1000, and `max_age_hours` is positive. `policy` is `warn`
or `block`. `method` is `navigation` or `interaction`; INP requires interactions,
never navigation-only Lighthouse or a TBT substitution. Scenario fields must
match exactly, including device (`mobile`/`desktop`) and cache (`cold`/`warm`).
Use stable scenario labels whose precise throttling, input, and data definitions
live beside the producer. A viewport label alone is not proof of mobile testing.

Project-owned browser tools emit `quality-runner-web-performance-evidence/v1`:

```json
{
  "schema": "quality-runner-web-performance-evidence/v1",
  "observed_at": "2026-11-03T12:00:00Z",
  "target": {
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "build_mode": "production",
    "build_id": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "tool": { "name": "project-browser-producer", "version": "1.0" },
  "command": "pnpm performance:measure",
  "measurements": [{
    "budget_id": "home-mobile-lcp",
    "metric": "lcp_ms",
    "method": "navigation",
    "scenario": {
      "route": "/", "journey": "home-load", "device": "mobile",
      "network": "slow-4g-v1", "cpu": "4x-v1", "cache": "cold", "dataset": "demo-v1"
    },
    "samples": [2100, 2200, 2300]
  }]
}
```

The IDs and digest above are placeholders. The producer must record the actual
commit, hash of the measured production build (with a documented hashing method),
tool version, and reproducible command. QR checks a clean tracked working tree
and exact HEAD, but does not hash the running build, authenticate the producer,
inspect untracked build inputs, or execute the recorded command. This is imported
measurement evidence, not independent attestation. Keep credentials and private
URLs/data out of scenario labels and commands: these fields appear in the report.

```sh
qr web-readiness /path/to/repository \
  --performance-evidence /path/to/web-performance-evidence.json --json
```

The import is bounded to 1 MiB, 1000 records, and 1000 samples per record. The
schema ships at `quality_runner/schemas/web-performance-evidence.schema.json`.
Malformed evidence, duplicate IDs, dirty tracked source, commit/context mismatch,
future/stale timestamps, or too few samples block the affected checks. Missing
receipts or measurements stay `unknown`; invalid budget configuration blocks
instead of silently dropping a budget. A valid aggregate at or below the maximum
passes; over-budget results fail. Each check retains its declared `warn`/`block`
policy. `warn` findings yield warnings, while unknown required checks keep the
report unknown and non-zero. Other source/deployment checks still apply, so a
passing performance budget alone cannot make a site deployment-ready.

Reports include samples, min/max, aggregate, sample count, producer, build,
scenario, and policy rationale. Performance checks remain `browser_rendered`
lab observations. Do not claim field Core Web Vitals compliance, population p75,
or faster user journeys from these values alone. Keep before/after revisions and
conditions comparable; this version enforces absolute budgets and does not invent
regression tolerances or rebaseline failures. Existing authorized field evidence
remains separate. No telemetry or new browser dependency is installed by QR.

Fleet's performance dimension includes these declared checks. Its source-only
scan does not import browser receipts, so missing measurements stay unknown
rather than being masked by a successful artifact budget. No fleet-wide budgets
are activated by this feature. Use the CLI JSON report as the machine interface;
there is no separate web-readiness MCP endpoint.
