# Release Checklist

Quality Runner publishes Python distributions from the `Release` GitHub Actions
workflow when a `v*.*.*` tag is pushed.

## PyPI

1. Confirm the local ladder passes:
   - `python3.14 -m pytest -q`
   - `ruff check .`
   - `ruff format --check .`
   - `basedpyright`
   - `vulture . --min-confidence 70`
   - `uv build`
2. Configure PyPI Trusted Publishing for `jakyeamos/quality-runner`.
3. Push a version tag, for example `v0.1.0`.
4. Confirm the GitHub Actions release workflow publishes the package.
5. Verify:
   - `uv tool install quality-runner`
   - `quality-runner --version`
   - `quality-runner doctor --json`

## Homebrew

Use `packaging/homebrew/quality-runner.rb` as the initial formula template after
the PyPI source distribution is live. Recompute the `sha256` from the published
source artifact before opening a tap PR.
