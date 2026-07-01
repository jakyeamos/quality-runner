# Dogfood Report

Date: 2026-06-28

Quality Runner was run against the committed fixture corpus under `fixtures/corpus`.

| Fixture | Expected status | Purpose |
| --- | --- | --- |
| `complete-js` | `clean` | Full JavaScript quality surface with pnpm, Pre-CR, smoke, pre-pr, and truth file. |
| `mature-mixed` | `planned` | Mixed Python/JS repo with Make, Docker, Terraform, migrations, OpenAPI, Protobuf, generated code, monorepo metadata, explicit local policy, and one deliberate missing dead-code gate. |
| `partial-js` | `planned` | Minimal JavaScript repo with only lint configured. |
| `python-empty` | `planned` | Python repo with no runnable quality commands configured. |

The corpus is intentionally small. It protects the baseline product contract:
clean repos stay clean, incomplete repos produce remediation slices, and all runs
write the public artifact set including `run-manifest.json`.

The `mature-mixed` fixture is the senior-review proxy. It proves Quality Runner
can distinguish broad mature-codebase evidence from actual missing quality
capabilities: Make targets, Docker runtime files, Terraform configuration, DB
migrations, service contracts, generated code, and monorepo task runners are
recognized as repo surfaces, while the intentionally absent dead-code gate stays
as the planned remediation item.
