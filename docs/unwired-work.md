# Unwired Work Detection

Quality Runner reports partially built or unwired work as structural category
`integrate`. These findings are different from ordinary dead-code findings:
they ask for an author decision before any cleanup is attempted.

## What QR Checks

The `integrate` scan looks for deterministic signals that work may have been
started but not connected:

- `stub-implementation`: `NotImplementedError`, bare `pass`, or ellipsis-only
  bodies in implementation code.
- `todo-scaffold`: TODO-heavy scaffold files in entrypoint-shaped paths or WIP
  contexts.
- `export-without-references`: exported or top-level symbols with no scanned
  source references outside their defining file.
- `handler-without-registration`: handler-shaped functions that are absent from
  configured registration files.
- `dead-code-unwired-candidate`: vulture or knip output reclassified as a wiring
  decision when the symbol or file looks like scaffolded WIP.

## Dead Code Versus Unwired Work

The `dead_code` capability still answers whether a repo has an executable
unused-code gate. Tool output from vulture or knip remains gate evidence.

`integrate` asks a narrower product question: was this work intentionally left
unwired, or did a feature stop before reaching an entrypoint? For that reason,
QR does not recommend deletion by default. Remediation slices ask the author to
choose one disposition:

- `wire`: connect the capability to a router, CLI, MCP registry, UI route, or
  public API surface, then add focused integration proof.
- `finish`: complete the implementation and remove stub paths.
- `descope`: remove the partial surface only after confirming it is out of
  scope, with rationale.
- `accept-wip`: record an `accepted-intentional` disposition with owner, reason,
  and optional expiry.

## Configuration

`integrate` checks run with the structural scan unless disabled:

```toml
[quality_runner.integrate]
enabled = true
registration_globs = ["**/cli.py", "**/router*.ts", "**/mcp.py"]
entrypoint_globs = ["**/main.*", "**/index.*", "apps/*/src/app/**"]
```

To disable the category:

```toml
[quality_runner.integrate]
enabled = false
```

`registration_globs` tell QR where handlers, subcommands, routes, or MCP tools
should appear when they are wired. `entrypoint_globs` help distinguish TODO-heavy
scaffolds from ordinary comments.

## Artifacts

`code-quality-scan.json` contains raw `integrate` findings. `quality-audit.json`
groups them as `structural:integrate` and marks actionability as
`needs-author-decision`.

`remediation-plan.json` emits `decide-wiring-*` slices with `action_groups` for
the four dispositions. Handoffs prefer these slices as `next_slice` when no gate
blocker is more urgent, so controllers see the author decision before ordinary
structural cleanup.
