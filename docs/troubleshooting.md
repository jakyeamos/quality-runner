# Troubleshooting

## `quality-runner` is not found

Install as a uv tool:

```bash
uv tool install git+https://github.com/jakyeamos/quality-runner.git
```

Then ensure the uv tool bin directory is on PATH:

```bash
echo "$PATH"
uv tool dir
```

On this machine, console scripts are exposed through `~/.local/bin`.

## Package build fails with top-level package discovery

Quality Runner explicitly packages only `quality_runner*`. Test helpers under
`test_support/` are not included in the distributable wheel.

Run:

```bash
uv build
```

## Pre-CR reports no coverage result

Quality Runner uses a custom LCOV helper:

```bash
python3.14 scripts/run_pytest_with_lcov.py
pre-cr run --workspace .
```

Documentation, workflow files, tests, and packaging metadata are excluded from
changed-line coverage surfaces.

## A run writes findings for missing capabilities

That is expected. Quality Runner reports missing quality surfaces such as lint,
typecheck, tests, dead-code checks, Pre-CR, and truth-file maintenance. The tool
does not install or create those surfaces automatically.
