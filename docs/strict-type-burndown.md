# Strict type-checking burndown

BasedPyright standard mode remains the certified repository gate. Strict mode
is a separate, advisory ratchet until its migration evidence supports
promotion.

The baseline is occurrence-aware and records the pinned tool/config identity:

```sh
uv run --locked python scripts/check_strict_baseline.py --update \
  --reason "initial strict inventory on merged main"
uv run --locked python scripts/check_strict_baseline.py
```

The first command is an intentional baseline change and must be reviewed with
the reason for the rebaseline. The second command exits with:

- `0` when strict diagnostics are unchanged or reduced;
- `1` when new diagnostics appear;
- `2` for invalid invocation/configuration;
- `3` when coverage, tool identity, or deterministic occurrence matching cannot
  be verified.

Repeated identical diagnostics are matched by stable source order. If a
repeated diagnostic group changes size, the command fails closed as unknown
instead of guessing which occurrence was added or resolved.

The initial burndown baseline is intentionally a measurement artifact. It does
not promote strict mode, waive findings, or replace the standard CI gate.
