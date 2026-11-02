# Strict type-checking burndown

The full declared package scope is checked in both standard and strict modes.
The strict cleanup was merged into `dev` in PR #18, and CI enforces the pinned
zero-diagnostic baseline. Branch reconciliation must preserve that cleanup
while applying the same strict checks to newly integrated modules.

The baseline is occurrence-aware and records the pinned tool/config identity:

```sh
uv run --locked basedpyright --project pyrightconfig.strict.json
uv run --locked python scripts/check_strict_baseline.py
```

The first command checks the source directly. The second checks diagnostics
and baseline identity, and exits with:

- `0` when strict diagnostics are unchanged or reduced;
- `1` when new diagnostics appear;
- `2` for invalid invocation/configuration;
- `3` when coverage, tool identity, or deterministic occurrence matching cannot
  be verified.

Repeated identical diagnostics are matched by stable source order. If a
repeated diagnostic group changes size, the command fails closed as unknown
instead of guessing which occurrence was added or resolved.

The baseline contains zero diagnostics. Do not use `--update` to accept new
debt. An intentional tool or configuration migration requires a reviewed
reason and fresh equivalent coverage; it must preserve the zero-error target.
The strict ratchet complements the standard CI check.
