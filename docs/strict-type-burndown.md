# Strict type-checking burndown

BasedPyright standard mode remains the certified repository gate. Strict mode
is a separate occurrence-aware ratchet while its existing diagnostics are
being resolved.

The strict scan is pinned by `uv.lock` and `pyrightconfig.strict.json`. Create
the reviewed baseline once with:

```sh
uv run --locked python scripts/check_strict_baseline.py --update \
  --reason "initial strict inventory on current repository"
```

Run the ratchet locally with:

```sh
uv run --locked python scripts/check_strict_baseline.py
```

The command records stable diagnostic occurrences, tool version, config hash,
coverage, and baseline provenance in
`docs/baselines/basedpyright-strict.json`. Fingerprints exclude line positions
so source movement does not look like progress. Repeated identical diagnostic
groups are matched by deterministic source order; a group-size change is
ambiguous and blocks the result rather than guessing.

Results are explicit:

- `passed` means the strict scan is clean.
- `blocked` means legacy diagnostics remain, or the scan/baseline evidence is
  incomplete or ambiguous. Legacy diagnostics are debt, not a pass.
- `failing` means at least one new strict diagnostic appeared and exits 1.

Exit 3 is reserved for evidence/configuration blockers. A baseline update is
an intentional policy change and requires a reviewed reason. The CI quality job
runs the same locked ratchet command after the certified standard-mode gate;
the release checks mirror it. Strict mode remains advisory until the baseline
is empty and its local, repeat-pass, intentional-failure, and CI evidence is
promoted deliberately.

Quality Runner's fleet maturity feed exposes two related dimensions. The
`strict_policy_visibility` dimension measures whether a supported type system's
strict policy is visible. It has adapters for BasedPyright/Pyright, TypeScript,
and mypy; a BasedPyright config plus deterministic baseline scores 4, a strict
TypeScript or mypy config scores 3, and a supported type surface without strict
configuration scores 1.
The `strict_type_debt` dimension measures the remaining debt with a bounded
0–4 score:
zero occurrences is 4, 1–10 is 3, 11–100 is 2, 101–1,000 is 1, and more than
1,000 is 0. When no supported strict-capable type surface exists, policy
visibility is not applicable rather than a penalty. When a supported surface
exists without strict configuration, it scores 1. The policy dimension measures
visibility; the debt dimension remains BasedPyright-specific until another
occurrence-aware ratchet exists; the ratchet command remains the evidence that
blocks new diagnostics.
