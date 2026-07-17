# Consumer Tooling

Quality Runner is the shared tool. Consumer repositories should not vendor a
copy of its packages or rely on a stale global `quality-runner` executable.
The old compatibility packages remain import-compatible, but their runtime
should come from the current QR tool surface.

## Always-current remote invocation

For a latest-main run from any repository:

```bash
uvx --refresh \
  --from git+https://github.com/jakyeamos/quality-runner.git \
  quality-runner refresh /path/to/repo --run-id-prefix qr-current --json
```

The QR checkout also contains `scripts/quality-runner`. Its default mode is
the same refreshing remote invocation, so a shared checkout can be used as a
stable command path without copying QR into every consumer:

```bash
/path/to/quality-runner/scripts/quality-runner \
  refresh /path/to/repo --run-id-prefix qr-current --json
```

## Local checkout invocation

Use the exact QR checkout when testing a branch or when a controller needs
source-local evidence:

```bash
QUALITY_RUNNER_MODE=local \
QUALITY_RUNNER_REPO=/path/to/quality-runner \
/path/to/quality-runner/scripts/quality-runner \
  refresh /path/to/repo --run-id-prefix qr-current --json
```

The direct equivalent is:

```bash
uv run --project /path/to/quality-runner quality-runner \
  refresh /path/to/repo --run-id-prefix qr-current --json
```

Local mode never pulls or updates the checkout. Latest mode refreshes the Git
tool environment on each invocation. Use a versioned or commit-specific source
only when reproducibility is more important than following the latest QR.

## Python package consumers

During local development, keep one QR path dependency and let the consumer
load the compatibility namespaces from that checkout. Run the consumer's
normal environment sync after changing the QR checkout. A locked published
package still requires an intentional dependency upgrade; invoking QR through
the tool surface is the path that avoids stale package imports in controller
and worker commands.

## Rollout provenance

`quality-runner rollout` records `quality_runner_version`,
`quality_runner_source`, and `quality_runner_command` in its result and ledger.
Generated controller reports use a source-aware command for the QR checkout
that produced them, rather than a bare PATH lookup that could resolve an old
v0.3.0 install.
