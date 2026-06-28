# Dogfood Report

Date: 2026-06-28

Quality Runner was run against the committed fixture corpus under `fixtures/corpus`.

| Fixture | Expected status | Purpose |
| --- | --- | --- |
| `complete-js` | `clean` | Full JavaScript quality surface with pnpm, Pre-CR, smoke, pre-pr, and truth file. |
| `partial-js` | `planned` | Minimal JavaScript repo with only lint configured. |
| `python-empty` | `planned` | Python repo with no runnable quality commands configured. |

The corpus is intentionally small. It protects the baseline product contract:
clean repos stay clean, incomplete repos produce remediation slices, and all runs
write the public artifact set including `run-manifest.json`.
