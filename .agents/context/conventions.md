# Implementation conventions

last_reviewed: 2026-08-11

Keep scans read-only and findings deterministic, bounded, redacted, and
machine-readable. Preserve configured, discovered, executed, passed, blocked,
unknown, and stale states instead of collapsing them. Schema or taxonomy changes
must update CLI/API docs, tests, plugin contracts, and feed consumers.
