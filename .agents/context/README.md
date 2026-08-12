# Quality Runner context index

last_reviewed: 2026-08-11

Load only the packet needed for the task.

- `commands.md` — quality, fleet, replay, and publication commands.
- `conventions.md` — finding, evidence, and compatibility rules.
- `failure-modes.md` — blocked execution and stale-evidence recovery.
- `examples.md` — canonical implementation and test examples.
- `done.md` — source, CLI, fleet, and consumer completion evidence.
- `README.md` — public command contract.
- `docs/integrations/pronto-maturity-feed.md` — Pronto feed contract.

Do not treat a source test, generated feed, or process exit as proof of the next
consumer surface. Preserve target-branch, checkout, execution, and freshness
provenance separately.
