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
