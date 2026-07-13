# Upgrade and Compatibility

## Release state

This branch is an unreleased `0.5.1` candidate. `v0.5.0` is the current
published compatibility baseline. The cutover policy below takes effect only
when `v0.5.1` is published; it does not claim that the candidate is available
from PyPI yet.

## Upgrade and rollback

After publication, upgrade the installed tool normally:

```bash
uv tool upgrade quality-runner
quality-runner doctor --json
```

To select the published candidate version explicitly:

```bash
uv tool upgrade 'quality-runner==0.5.1'
```

No artifact conversion is required. Existing `.quality-runner/` runs remain
readable by the v1 artifact readers. V2 outcomes are presentation contracts
derived from the same local evidence; Fresh Review lifecycle files are
additive. Keep existing evidence in place while you validate the upgrade.

If a published `0.5.1` needs to be rolled back, preserve the run directory and
reinstall the prior package:

```bash
uv tool install 'quality-runner==0.5.0' --force
uv tool list
"$(uv tool dir)/quality-runner/bin/python" -c 'from importlib.metadata import version; print(version("quality-runner"))'
```

`v0.5.0` has a historical runtime-display mismatch: `quality-runner --version`
and its doctor payload report `0.4.0` even when the installed package metadata
is `0.5.0`. Use `uv tool list` or the metadata command above to verify the
rollback target; do not use the v0.5.0 runtime display as version proof.

There is no destructive downgrade step. Do not delete artifacts merely to make
the older tool run; remove local evidence only under your repository's normal
retention policy.

## CLI cutover

New work should use the outcome-first journeys:

| Existing v1 path | Preferred v2 path | Compatibility note |
| --- | --- | --- |
| `inspect` | `audit --inspect-only` | Discovery-only outcome. |
| `run` | `audit` | Audit-and-plan outcome. |
| `verify-gates` | `verify` | Evidence-only or explicitly authorized disposable execution. |
| `review --legacy-output` | `review` | Review now emits the v2 outcome by default. |
| `status` | `runs` where bounded history is enough | Not a one-to-one replacement; keep `status` for its existing v1 view. |
| `refresh` | No direct replacement | Retained for the established combined controller workflow. |

`review --outcome` remains a harmless alias for the default. Pass
`--legacy-output` only when an existing CLI consumer requires the established
v1 field shape. Its warning is written to stderr, so its JSON stdout stays
machine-readable; use the default v2 outcome for packet-ready assessment and
next-action guidance.

## Support window

Once `0.5.1` is published, v1 CLI paths that have a direct outcome replacement
(`inspect`, `run`, `verify-gates`, and `review --legacy-output`) are supported
through `0.7.x`. They will not be removed before `0.8.0`, except for a
security-critical change that cannot safely retain a legacy behavior.

`quality_runner_status`, `refresh`, `quality_evidence_contract`, and
`repo_quality_certifier` do not have a retirement schedule because they do not
all have direct v2 equivalents. Their existing public contracts remain
compatibility islands.

## MCP compatibility

New MCP integrations should use the four outcome tools advertised by
`tools/list`. The legacy MCP tools retain their established v1
`structuredContent` shapes; this cutover does not add fields to those payloads.
`quality_runner_inspect_repo`, `quality_runner_run`, and
`quality_runner_review` identify their direct replacements and support window
in tool descriptions. See [MCP Integration](mcp.md) for the protocol boundary.

For the release procedure and the built-distribution checks that enforce this
policy, see the [Release Checklist](release.md). For the local-evidence handling
rules that apply during an upgrade or rollback, see the
[Artifact Contract](artifacts.md).
